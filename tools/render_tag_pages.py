#!/usr/bin/env python3
"""Pre-generate Jekyll tag pages from data/papers-*.json.

For each canonical tag × time window, writes one page like
docs/tag/dft-30d.md listing matching papers sorted by `updated` desc.

Windows: 7d, 30d, 90d, 360d, all. URL stays bookmark-friendly:
   <site>/tag/dft-30d/  →  recent DFT papers, last 30 days
"""
import argparse
import html
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io
import tag_matcher

LOG = logging.getLogger("render_tag_pages")

WINDOWS = [
    ("7d", 7),
    ("30d", 30),
    ("90d", 90),
    ("360d", 360),
    ("all", None),
]

DEFAULT_OUT = data_io.ROOT / "docs" / "tag"


def _slug(text):
    """GitHub-flavored slug for a heading anchor."""
    s = text.lower()
    s = "".join(c if (c.isalnum() or c in " -_") else "" for c in s)
    return s.replace(" ", "-")


def _within_window(updated_str, days):
    if days is None:
        return True
    cutoff = date.today() - timedelta(days=days)
    return datetime.strptime(updated_str, "%Y-%m-%d").date() >= cutoff


def _render_page(tag, window_label, papers, all_tag_windows_for_nav):
    """Compose one tag-page markdown."""
    lines = []
    # Jekyll frontmatter — needed so the page is rendered with the site layout.
    lines.append("---")
    lines.append("layout: page")
    lines.append(f'title: "{tag} ({window_label})"')
    lines.append(f"current_tag: {tag}")
    lines.append(f"current_window: {window_label}")
    lines.append("---")
    lines.append("")
    # Compact one-line header: title | count | window switcher | back link.
    nav_parts = []
    for w in all_tag_windows_for_nav:
        if w == window_label:
            nav_parts.append(f"<strong>{html.escape(w)}</strong>")
        else:
            nav_parts.append(
                f'<a href="{html.escape(tag)}-{html.escape(w)}.html">'
                f"{html.escape(w)}</a>")
    nav_html = " ".join(nav_parts)
    lines.append('<header class="tag-header">')
    lines.append(f'  <h1>{html.escape(tag)} — {html.escape(window_label)}</h1>')
    lines.append(f'  <span class="paper-count">{len(papers)} papers</span>')
    lines.append(f'  <nav class="window-nav">{nav_html}</nav>')
    lines.append('  <a class="back-link" href="../">← all tags</a>')
    lines.append('</header>')
    lines.append("")
    if papers:
        # Raw HTML table — Jekyll/kramdown passes it through untouched. We need
        # HTML (not markdown table) because each paper gets a SECOND row with
        # its other tags as window-aware links, and markdown tables don't
        # support row spans / styled secondary rows.
        lines.append('<table class="papers">')
        lines.append("<thead><tr><th>Date</th><th>Title</th>"
                     "<th>Authors</th><th>arXiv</th></tr></thead>")
        lines.append("<tbody>")
        for pid, rec in papers:
            title = html.escape(rec["title"].replace("\n", " "))
            authors = html.escape(rec["first_author"]) + (
                " et al." if len(rec["authors"]) > 1 else "")
            # Title becomes a popup-link. JS intercepts click → fetches the
            # HTML fragment from /abstracts/<id>.html and shows it in a modal.
            # Without JS, the link still resolves to the standalone fragment.
            title_link = (
                f'<a class="abstract-popup paper-title-link" '
                f'href="../abstracts/{html.escape(pid)}.html">{title}</a>')
            # Per-paper tags as a sub-line, window-aware. Current tag skipped.
            other_tags = [t for t in rec.get("tags", []) if t != tag]
            if other_tags:
                tag_links = " · ".join(
                    f'<a href="{html.escape(t)}-{window_label}.html">'
                    f'{html.escape(t)}</a>'
                    for t in other_tags)
                title_cell = (
                    f'<div class="paper-title">{title_link}</div>'
                    f'<div class="paper-tags">{tag_links}</div>')
            else:
                title_cell = f'<div class="paper-title">{title_link}</div>'
            lines.append('<tr class="paper">')
            lines.append(f'<td>{rec["updated"]}</td>')
            lines.append(f'<td>{title_cell}</td>')
            lines.append(f'<td>{authors}</td>')
            lines.append(
                f'<td><a href="http://arxiv.org/abs/{pid}">{pid}</a></td>')
            lines.append("</tr>")
        lines.append("</tbody></table>")
    else:
        lines.append("_No papers in this window._")
    lines.append("")
    return "\n".join(lines)


def run(canonical_path, out_dir):
    canonical = tag_matcher.load_canonical_tags(canonical_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Bucket papers by tag for fast lookup.
    by_month, _ = data_io.load_all_months()
    papers_by_tag = defaultdict(list)
    for month, papers in by_month.items():
        for pid, rec in papers.items():
            for t in rec.get("tags", []):
                papers_by_tag[t].append((pid, rec))

    files_written = 0
    window_labels = [w[0] for w in WINDOWS]
    for tag in canonical:
        tag_papers = papers_by_tag.get(tag, [])
        # Sort once per tag
        tag_papers.sort(key=lambda x: x[1]["updated"], reverse=True)
        for window_label, days in WINDOWS:
            in_window = [p for p in tag_papers
                         if _within_window(p[1]["updated"], days)]
            page = _render_page(tag, window_label, in_window, window_labels)
            out_path = out_dir / f"{tag}-{window_label}.md"
            out_path.write_text(page, encoding="utf-8")
            files_written += 1

    LOG.info(f"wrote {files_written} files to {out_dir}")
    return {
        "files_written": files_written,
        "tags": len(canonical),
        "papers_with_tag": sum(1 for v in papers_by_tag.values() if v),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", default=None,
                        help="path to canonical.yaml (default: tags/canonical.yaml)")
    parser.add_argument("--out-dir", default=None,
                        help=f"output dir (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    canonical_path = Path(args.canonical) if args.canonical else (
        data_io.ROOT / "tags" / "canonical.yaml")
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT
    run(canonical_path, out_dir)


if __name__ == "__main__":
    main()
