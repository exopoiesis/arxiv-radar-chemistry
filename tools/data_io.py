"""Shared I/O, rendering, and filtering helpers for the arxiv-radar pipeline.

Acts as the base library — backfill.py, daily_arxiv.py, render_*.py, and
filter_corpus.py all import from here.

Schema (per paper, stored in data/papers-YYYY-MM.json keyed by arxiv_id):
    title, first_author, authors[], abstract, primary_category, categories[],
    published (YYYY-MM-DD), updated (YYYY-MM-DD), comment, pdf_url,
    topics[]  — names from config.yaml
    tags[]    — canonical tags (Phase 2)
"""
import html as html_mod
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ABSTRACTS_DIR = ROOT / "abstracts"
DOCS_ABSTRACTS_DIR = ROOT / "docs" / "abstracts"


# -- Chemistry filter ----------------------------------------------------------
# Word-boundary regex of chemistry-relevant terms. Stems (chemistr, molecul)
# catch inflections; short abbreviations (DFT, MOF) are bound to whole-word
# matches via \b. Used by:
#   - filter_corpus.py for batch post-processing
#   - backfill.py / daily_arxiv.py for inline filter on incoming papers
#   - tests in test_data_io.py
CHEM_PATTERN = re.compile(
    r"\b(?:"
    r"chemistr\w*|chemical\w*|molecul\w*|molecule\w*|"
    r"material\w*|compound\w*|"
    r"drug\w*|pharmaceutic\w*|"
    r"protein\w*|peptid\w*|enzyme\w*|amino\s+acid|"
    r"reaction\w*|catalys\w*|catalytic|synthes\w*|retrosynthes\w*|"
    r"polymer\w*|"
    r"crystal\w*|lattice\w*|"
    r"dft|density\s+functional|first[-\s]principles|ab\s+initio|"
    r"nanoparticle\w*|nanomater\w*|"
    r"biomolecul\w*|ligand\w*|"
    r"battery|electrolyt\w*|"
    r"electrocataly\w*|photocataly\w*|"
    r"mof|mofs|cof|cofs|zeolite\w*|"
    r"electronic\s+structure|adsorpt\w*|adsorbent\w*|"
    r"covalent|noncovalent|hydrogen\s+bond|"
    r"molecular\s+dynamics|smiles|"
    r"qsar|qspr|admet|"
    r"perovskite\w*|alloy\w*|"
    r"force\s+field\w*"
    r")\b",
    re.IGNORECASE,
)


def is_chemistry_paper(abstract):
    """True if abstract contains at least one chemistry-context term."""
    if not abstract:
        return False
    return bool(CHEM_PATTERN.search(abstract))


# -- URL linkification ---------------------------------------------------------
# Wrap bare URLs in markdown link syntax so they're clickable in rendered
# abstract files. Bare URLs auto-link on github.com but not in every renderer
# (Pages with custom themes, copies, IDEs); explicit [url](url) is universal.
# Skips URLs already inside markdown link syntax `](url)` — avoids double-wrap.
_BARE_URL_RE = re.compile(
    r"(?<!\]\()"               # not preceded by '](' (already in markdown link)
    r"(https?://[^\s<>\[\]()]+)",
    re.IGNORECASE,
)
_TRAILING_PUNCT = ".,;:!?\"'"


def linkify_urls(text):
    """Replace bare URLs in `text` with `[url](url)` markdown links.

    Trailing punctuation (period, comma, etc) stays outside the link — common
    pattern in arxiv abstracts: 'see https://github.com/foo/bar.'
    """
    if not text:
        return text

    def replace(m):
        url = m.group(1)
        trailing = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return m.group(0)
        return f"[{url}]({url}){trailing}"

    return _BARE_URL_RE.sub(replace, text)


# -- Config / query parsing ----------------------------------------------------
def load_keyword_queries(config_path):
    """Read config.yaml and produce per-topic arXiv search query strings.

    Each filter list becomes an OR-joined query. Per-filter rules:
      - Plain phrase with spaces → quoted: "Graph Neural Networks"
      - Single word → bare: GNN
      - Prefix 'RAW:' → expression passed through, wrapped in parens.
        Lets you write compound queries:
            RAW:"Large Language Models" AND (chemistry OR molecular)
        Used to AND a greedy filter with a chemistry context, sparing
        download bandwidth on irrelevant ML noise.
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    queries = {}
    for topic, meta in cfg["keywords"].items():
        parts = []
        for f in meta["filters"]:
            if f.startswith("RAW:"):
                parts.append(f"({f[4:]})")
            elif " " in f:
                parts.append(f'"{f}"')
            else:
                parts.append(f)
        queries[topic] = " OR ".join(parts)
    return queries


def load_all_months():
    """Load every data/papers-YYYY-MM.json into memory.

    Returns:
        by_month: dict[str, dict[str, record]] keyed by 'YYYY-MM'
        pid_to_month: dict[str, str] for O(1) "which month holds this pid"
    """
    by_month = defaultdict(dict)
    pid_to_month = {}
    for f in sorted(DATA_DIR.glob("papers-*.json")):
        month = f.stem.replace("papers-", "")
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        by_month[month] = data
        for pid in data:
            pid_to_month[pid] = month
    return by_month, pid_to_month


def save_month(by_month, month):
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"papers-{month}.json"
    tmp = out.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(by_month[month], f, ensure_ascii=False, indent=1, sort_keys=True)
    tmp.replace(out)


def paper_to_record(r):
    """Convert arxiv.Result → (arxiv_id, record dict). arxiv_id has version stripped."""
    pid = r.get_short_id()
    v_pos = pid.find("v")
    if v_pos != -1:
        pid = pid[:v_pos]
    return pid, {
        "title": r.title.strip(),
        "first_author": str(r.authors[0]) if r.authors else "",
        "authors": [str(a) for a in r.authors],
        "abstract": r.summary.replace("\n", " ").strip(),
        "primary_category": r.primary_category,
        "categories": list(r.categories),
        "published": r.published.date().isoformat(),
        "updated": r.updated.date().isoformat(),
        "comment": r.comment,
        "pdf_url": f"http://arxiv.org/pdf/{pid}",
        "topics": [],
        "tags": [],
    }


def iter_papers_in_window(by_month, days):
    """Yield (pid, rec) for papers with `updated` within last `days` from today."""
    cutoff = date.today() - timedelta(days=days)
    for month_data in by_month.values():
        for pid, rec in month_data.items():
            if datetime.strptime(rec["updated"], "%Y-%m-%d").date() >= cutoff:
                yield pid, rec


def abstract_path(pid, rec=None):
    """abstracts/<pid>.md — flat layout, arxiv IDs are unique.

    Year subdirs were dropped because the original-publication year felt like
    a stale label on README links to papers whose latest revision is recent
    (e.g. id 2503.04492 with updated 2026-04 surfaced as a 2025/ link).
    `rec` arg kept for backwards-compat with callers that pass it.
    """
    return ABSTRACTS_DIR / f"{pid}.md"


def write_abstract(pid, rec, force=False):
    """Write abstracts/<pid>.md if missing (or force=True). Returns True if written.

    Idempotent — safe to call repeatedly. Used both by batch render_abstracts.py
    and inline by fetchers (backfill.py, daily_arxiv.py) when adding new papers.
    """
    out = abstract_path(pid, rec)
    if out.exists() and not force:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_abstract_md(pid, rec), encoding="utf-8")
    return True


def render_abstract_md(pid, rec):
    """Render a paper as a clean markdown abstract page.

    Layout (what user sees when opening the file from README):
        1. Title (h1) — page heading
        2. Authors line
        3. Abstract body (with linkified URLs)
        4. Horizontal rule
        5. Service metadata: Published/Updated, Topics, Tags, arXiv categories
        6. Links to arxiv page + PDF

    No YAML frontmatter — data already lives in data/papers-*.json. Keeps the
    raw GitHub view clean (no ugly key:value block before the content).
    """
    lines = []
    lines.append(f"# {rec['title']}")
    lines.append("")
    lines.append(f"**Authors:** {', '.join(rec['authors'])}")
    lines.append("")
    lines.append(linkify_urls(rec["abstract"]))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**Published:** {rec['published']} | **Updated:** {rec['updated']}")
    lines.append("")
    if rec.get("topics"):
        lines.append(f"**Topics:** {', '.join(rec['topics'])}")
        lines.append("")
    if rec.get("tags"):
        lines.append(f"**Tags:** {', '.join(rec['tags'])}")
        lines.append("")
    lines.append(f"**arXiv categories:** {', '.join(rec['categories'])}")
    lines.append("")
    lines.append(f"[arXiv abstract page](http://arxiv.org/abs/{pid}) | [PDF]({rec['pdf_url']})")
    lines.append("")
    return "\n".join(lines)


# -- HTML abstract fragments (popup-ready, served from docs/abstracts/) -------
_HTML_BARE_URL_RE = re.compile(
    r"(https?://[^\s<>\[\]()]+)",
    re.IGNORECASE,
)


def _linkify_html(text):
    """Linkify bare URLs after escape (returns HTML-safe string)."""
    escaped = html_mod.escape(text or "")

    def repl(m):
        url = m.group(1)
        trailing = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return m.group(0)
        return f'<a href="{url}" rel="nofollow noopener">{url}</a>{trailing}'
    return _HTML_BARE_URL_RE.sub(repl, escaped)


def render_abstract_html_fragment(pid, rec):
    """Render a paper as an HTML fragment ready for popup or standalone view.

    Output is a single <article class="abstract-fragment">; no <html>/<head>
    wrapper. The popup JS injects this directly into the modal via innerHTML;
    direct URL access (rare) shows it bare but readable.

    All user-controlled content is HTML-escaped; URLs in abstract are linkified
    after escaping to prevent injection.
    """
    title = html_mod.escape(rec.get("title", "").strip())
    authors = html_mod.escape(", ".join(rec.get("authors", [])))
    abstract_html = _linkify_html(rec.get("abstract", ""))
    primary_cat = html_mod.escape(rec.get("primary_category", ""))
    published = html_mod.escape(rec.get("published", ""))
    updated = html_mod.escape(rec.get("updated", ""))
    pdf_url = html_mod.escape(rec.get("pdf_url", ""))

    parts = [f'<article class="abstract-fragment" data-id="{html_mod.escape(pid)}">']
    parts.append(f'<h1 class="abstract-title">{title}</h1>')
    if authors:
        parts.append(f'<p class="abstract-authors">{authors}</p>')

    meta_bits = []
    meta_bits.append(
        f'<a href="http://arxiv.org/abs/{html_mod.escape(pid)}" '
        f'rel="nofollow noopener">arXiv:{html_mod.escape(pid)}</a>')
    if primary_cat:
        meta_bits.append(html_mod.escape(primary_cat))
    if published:
        meta_bits.append(f"Published {published}")
    if updated and updated != published:
        meta_bits.append(f"Updated {updated}")
    parts.append(
        '<p class="abstract-meta">' + '<span class="sep">·</span>'.join(
            f'<span>{b}</span>' for b in meta_bits) + '</p>')

    parts.append(f'<div class="abstract-body">{abstract_html}</div>')

    topics = rec.get("topics") or []
    if topics:
        parts.append(
            '<p class="abstract-tagline"><span class="label">Topics</span>'
            + html_mod.escape(", ".join(topics)) + '</p>')
    tags = rec.get("tags") or []
    if tags:
        tag_links = " ".join(
            f'<a href="../tag/{html_mod.escape(t)}-30d.html">{html_mod.escape(t)}</a>'
            for t in tags)
        parts.append(
            '<p class="abstract-tagline"><span class="label">Tags</span>'
            + tag_links + '</p>')

    cats = rec.get("categories") or []
    if cats:
        parts.append(
            '<p class="abstract-tagline"><span class="label">arXiv categories</span>'
            + html_mod.escape(", ".join(cats)) + '</p>')

    parts.append(
        '<p class="abstract-actions">'
        f'<a href="http://arxiv.org/abs/{html_mod.escape(pid)}" '
        'rel="nofollow noopener">arXiv abstract page</a>'
        f'<a href="{pdf_url}" rel="nofollow noopener">PDF</a>'
        '</p>')

    parts.append('</article>')
    return "\n".join(parts) + "\n"


def docs_abstract_path(pid):
    """docs/abstracts/<pid>.html — flat (arxiv IDs are unique)."""
    return DOCS_ABSTRACTS_DIR / f"{pid}.html"


def write_abstract_html(pid, rec, force=False):
    """Write docs/abstracts/<pid>.html. Idempotent unless force."""
    out = docs_abstract_path(pid)
    if out.exists() and not force:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_abstract_html_fragment(pid, rec), encoding="utf-8")
    return True


def render_md_row(pid, rec):
    """One row of the README table: |Date|Title|Authors|PDF|Abstract|"""
    date_s = rec["updated"]
    title = rec["title"].replace("|", "\\|").replace("\n", " ")
    authors = rec["first_author"]
    extra = " et al." if len(rec["authors"]) > 1 else ""
    abstract_link = f"abstracts/{pid}.md"
    return (
        f"|**{date_s}**|**{title}**|{authors}{extra}|"
        f"[{pid}](http://arxiv.org/abs/{pid})|"
        f"[md]({abstract_link})|"
    )
