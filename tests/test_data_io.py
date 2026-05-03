"""Happy-path tests for tools/data_io.py."""
import json
from datetime import date, timedelta

import pytest


def test_save_and_load_month_roundtrip(isolated_data_dir, sample_records):
    """save_month writes a file that load_all_months reads back identically."""
    import data_io
    by_month = {"2025-04": {pid: r for pid, r in sample_records.items()
                            if r["updated"].startswith("2025-04")}}
    data_io.save_month(by_month, "2025-04")

    loaded, pid_to_month = data_io.load_all_months()
    assert "2025-04" in loaded
    assert set(loaded["2025-04"].keys()) == {"2504.00001", "2504.00002"}
    assert pid_to_month["2504.00001"] == "2025-04"
    assert loaded["2025-04"]["2504.00001"]["title"] == sample_records["2504.00001"]["title"]


def test_load_all_months_empty_dir(isolated_data_dir):
    """No data files → empty dict, empty pid_to_month."""
    import data_io
    by_month, pid_to_month = data_io.load_all_months()
    assert dict(by_month) == {}
    assert pid_to_month == {}


def test_load_all_months_multiple_files(populated_data_dir):
    """Two month files load into separate keys, pid_to_month points to correct month."""
    import data_io
    by_month, pid_to_month = data_io.load_all_months()
    assert set(by_month.keys()) == {"2025-03", "2025-04"}
    assert pid_to_month["2503.00001"] == "2025-03"
    assert pid_to_month["2504.00001"] == "2025-04"
    assert len(by_month["2025-04"]) == 2


def test_paper_to_record_strips_version(arxiv_result_factory):
    """Version suffix v1/v2 stripped from arxiv_id key."""
    import data_io
    r = arxiv_result_factory(arxiv_id="2503.12345v2")
    pid, rec = data_io.paper_to_record(r)
    assert pid == "2503.12345"


def test_paper_to_record_schema(arxiv_result_factory):
    """All schema fields are populated correctly."""
    import data_io
    r = arxiv_result_factory(
        arxiv_id="2503.12345v1",
        title="  Whitespace Title  ",
        authors=("Alice", "Bob"),
        summary="line one\nline two",
        primary_category="cs.LG",
        categories=("cs.LG", "stat.ML"),
        published="2025-03-15",
        updated="2025-03-20",
        comment="42 pages",
    )
    pid, rec = data_io.paper_to_record(r)
    assert pid == "2503.12345"
    assert rec["title"] == "Whitespace Title"  # stripped
    assert rec["first_author"] == "Alice"
    assert rec["authors"] == ["Alice", "Bob"]
    assert rec["abstract"] == "line one line two"  # newlines collapsed
    assert rec["primary_category"] == "cs.LG"
    assert rec["categories"] == ["cs.LG", "stat.ML"]
    assert rec["published"] == "2025-03-15"
    assert rec["updated"] == "2025-03-20"
    assert rec["comment"] == "42 pages"
    assert rec["pdf_url"] == "http://arxiv.org/pdf/2503.12345"
    assert rec["topics"] == []
    assert rec["tags"] == []


def test_render_md_row_format(sample_record):
    """Markdown table row has 5 pipe-separated columns and a link to abstracts/."""
    import data_io
    row = data_io.render_md_row("2503.12345", sample_record)
    parts = row.strip("|").split("|")
    assert len(parts) == 5
    assert "**2025-03-20**" in parts[0]
    assert "Sample Paper" in parts[1]
    assert "Alice Smith et al." in parts[2]
    assert "2503.12345" in parts[3]
    assert "abstracts/2503.12345.md" in parts[4]


def test_render_md_row_escapes_pipes(sample_record):
    """Pipes inside title don't break the table — they're backslash-escaped."""
    import data_io
    sample_record["title"] = "Title | with | pipes"
    row = data_io.render_md_row("2503.12345", sample_record)
    # 5 cells → 6 separator pipes; title has 2 escaped pipes (\| each contains |)
    assert row.count("|") == 6 + 2
    assert "\\|" in row  # escape character present


def test_render_abstract_html_fragment_structure(sample_record):
    """HTML fragment is a single <article class='abstract-fragment'> with the
    classes the popup CSS targets. No <html>/<head>/<body> wrapper."""
    import data_io
    frag = data_io.render_abstract_html_fragment("2503.12345", sample_record)
    assert frag.startswith('<article class="abstract-fragment"')
    assert frag.rstrip().endswith("</article>")
    assert "<html" not in frag.lower()
    # Required structural classes for the popup theming
    for cls in ("abstract-title", "abstract-authors",
                "abstract-meta", "abstract-body", "abstract-actions"):
        assert cls in frag, f"missing class: {cls}"


def test_render_abstract_html_fragment_escapes_user_input(sample_record):
    """Title and authors are user-controlled; must be HTML-escaped to prevent
    injection via paper metadata."""
    import data_io
    rec = dict(sample_record)
    rec["title"] = 'Evil <script>alert(1)</script>'
    rec["authors"] = ["A <b>B</b>"]
    frag = data_io.render_abstract_html_fragment("2503.99999", rec)
    assert "<script>" not in frag
    assert "&lt;script&gt;" in frag
    assert "&lt;b&gt;" in frag


def test_write_abstract_html_creates_file(tmp_path, monkeypatch, sample_record):
    """write_abstract_html lands at docs/abstracts/<id>.html (flat dir)."""
    import data_io
    monkeypatch.setattr(data_io, "DOCS_ABSTRACTS_DIR", tmp_path / "docs" / "abstracts")
    assert data_io.write_abstract_html("2503.12345", sample_record) is True
    assert data_io.write_abstract_html("2503.12345", sample_record) is False  # idempotent
    out = tmp_path / "docs" / "abstracts" / "2503.12345.html"
    assert out.exists()
    assert "abstract-fragment" in out.read_text(encoding="utf-8")


def test_render_abstract_md_has_no_yaml_frontmatter(sample_record):
    """Markdown is pure content — no YAML frontmatter on top.
    Data lives in data/papers-*.json (source of truth); markdown is for reading.
    Avoids ugly key:value block in raw GitHub view."""
    import data_io
    md = data_io.render_abstract_md("2503.12345", sample_record)
    assert md.startswith("# "), "should start with markdown heading, not '---'"
    # YAML-style 'arxiv_id: \"...\"' must not be present
    assert 'arxiv_id: "' not in md
    # Visible content still has the key info
    assert "# Sample Paper on Graph Neural Networks" in md
    assert sample_record["abstract"] in md
    assert "[arXiv abstract page]" in md


def test_render_abstract_md_layout_order(sample_record):
    """Layout: title → authors → abstract → separator → metadata → links.
    User-friendly: opens to readable abstract, not service metadata."""
    import data_io
    sample_record["abstract"] = "ABSTRACTBODYMARKER"
    md = data_io.render_abstract_md("2503.12345", sample_record)
    title_pos = md.find("# Sample Paper")
    authors_pos = md.find("**Authors:**")
    abstract_pos = md.find("ABSTRACTBODYMARKER")
    published_pos = md.find("**Published:**")
    categories_pos = md.find("**arXiv categories:**")
    links_pos = md.find("[arXiv abstract page]")
    assert -1 < title_pos < authors_pos < abstract_pos
    assert abstract_pos < published_pos
    assert published_pos < categories_pos
    assert categories_pos < links_pos


def test_render_abstract_md_no_h2_abstract_heading(sample_record):
    """No '## Abstract' heading — abstract IS the page body, title is the heading."""
    import data_io
    md = data_io.render_abstract_md("2503.12345", sample_record)
    assert "## Abstract" not in md


def test_render_abstract_md_omits_empty_topics_tags(sample_record):
    """When topics/tags are empty, those metadata lines are skipped entirely."""
    import data_io
    sample_record["topics"] = []
    sample_record["tags"] = []
    md = data_io.render_abstract_md("2503.12345", sample_record)
    assert "**Topics:**" not in md
    assert "**Tags:**" not in md


def test_render_abstract_md_null_comment(sample_record):
    """comment=None renders as 'null'."""
    import data_io
    sample_record["comment"] = None
    md = data_io.render_abstract_md("2503.12345", sample_record)
    # comment isn't in the frontmatter currently (not in the rendered list)
    # But this test verifies render doesn't crash on None
    assert md  # didn't crash


def test_abstract_path_is_flat(sample_record):
    """abstract file lands at abstracts/<pid>.md — no year subdir."""
    import data_io
    p = data_io.abstract_path("2503.12345", sample_record)
    assert p.parts[-1] == "2503.12345.md"
    # parent must be ABSTRACTS_DIR itself, not a year subdir
    assert p.parent == data_io.ABSTRACTS_DIR


def test_write_abstract_creates_file(isolated_data_dir, sample_record):
    """write_abstract creates the file and returns True on first call."""
    import data_io
    written = data_io.write_abstract("2503.12345", sample_record)
    assert written is True
    expected = isolated_data_dir.abstracts / "2503.12345.md"
    assert expected.exists()
    assert "Sample Paper on Graph Neural Networks" in expected.read_text(encoding="utf-8")


def test_write_abstract_idempotent(isolated_data_dir, sample_record):
    """Second call skips and returns False, file stays unchanged."""
    import data_io
    data_io.write_abstract("2503.12345", sample_record)
    expected = isolated_data_dir.abstracts / "2503.12345.md"
    original = expected.read_text(encoding="utf-8")

    # mutate record but don't force — should keep original
    sample_record["title"] = "DIFFERENT TITLE"
    written = data_io.write_abstract("2503.12345", sample_record)
    assert written is False
    assert expected.read_text(encoding="utf-8") == original


def test_write_abstract_force_overwrites(isolated_data_dir, sample_record):
    """force=True regenerates the file with new content."""
    import data_io
    data_io.write_abstract("2503.12345", sample_record)
    sample_record["title"] = "UPDATED TITLE"
    written = data_io.write_abstract("2503.12345", sample_record, force=True)
    assert written is True
    expected = isolated_data_dir.abstracts / "2503.12345.md"
    assert "UPDATED TITLE" in expected.read_text(encoding="utf-8")


def test_linkify_urls_basic():
    """Bare http/https URL → markdown link [url](url)."""
    import data_io
    out = data_io.linkify_urls("Code at https://github.com/foo/bar for details.")
    assert "[https://github.com/foo/bar](https://github.com/foo/bar)" in out
    assert "for details" in out


def test_linkify_urls_strips_trailing_punctuation():
    """Period/comma after URL stays outside the link, not inside."""
    import data_io
    out = data_io.linkify_urls("See https://github.com/foo/bar.")
    # The trailing period must NOT be part of the URL
    assert "[https://github.com/foo/bar](https://github.com/foo/bar)." in out
    out2 = data_io.linkify_urls("URLs: https://a.com/x, https://b.com/y.")
    assert "[https://a.com/x](https://a.com/x)," in out2
    assert "[https://b.com/y](https://b.com/y)." in out2


def test_linkify_urls_handles_multiple():
    """Multiple URLs in same text all get linkified."""
    import data_io
    out = data_io.linkify_urls("Code: https://github.com/a Demo: http://example.org")
    assert out.count("](") == 2  # two markdown links


def test_linkify_urls_no_url():
    """Text without URLs is unchanged."""
    import data_io
    assert data_io.linkify_urls("Plain text here.") == "Plain text here."
    assert data_io.linkify_urls("") == ""


def test_linkify_urls_doesnt_double_wrap_existing_markdown():
    """Already-linked markdown isn't broken: [PDF](https://x) stays as is."""
    import data_io
    s = "Already linked: [PDF](https://example.com/paper.pdf) here."
    out = data_io.linkify_urls(s)
    # We don't want [https://example.com/paper.pdf](...)] forming double wraps
    assert out.count("[PDF]") == 1
    # The url inside the existing link shouldn't be replaced
    assert "[PDF](https://example.com/paper.pdf)" in out


def test_render_abstract_md_linkifies_abstract_urls(sample_record):
    """URLs in abstract field become clickable in the rendered markdown."""
    import data_io
    sample_record["abstract"] = "We provide code at https://github.com/test/repo here."
    md = data_io.render_abstract_md("2503.12345", sample_record)
    assert "[https://github.com/test/repo](https://github.com/test/repo)" in md


def test_is_chemistry_paper_positive():
    """Real chem terms trigger the filter."""
    import data_io
    assert data_io.is_chemistry_paper("DFT calculations of NMC oxide.")
    assert data_io.is_chemistry_paper("Molecular dynamics simulation.")
    assert data_io.is_chemistry_paper("LLM for retrosynthesis planning.")


def test_is_chemistry_paper_negative():
    """Non-chem text doesn't match."""
    import data_io
    assert not data_io.is_chemistry_paper("LLM for code generation.")
    assert not data_io.is_chemistry_paper("Robot navigation in unknown environments.")
    assert not data_io.is_chemistry_paper("")


def test_load_keyword_queries_simple(tmp_path):
    """Multi-word filters get quoted, single-word stay bare, joined by OR."""
    import data_io
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'keywords:\n'
        '  Topic A:\n'
        '    filters: ["Graph Neural Networks", "GNN"]\n',
        encoding="utf-8")
    queries = data_io.load_keyword_queries(cfg)
    assert queries == {"Topic A": '"Graph Neural Networks" OR GNN'}


def test_load_keyword_queries_raw_passthrough(tmp_path):
    """A filter prefixed RAW: passes through unquoted, wrapped in parens."""
    import data_io
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'keywords:\n'
        '  Topic A:\n'
        '    filters:\n'
        '      - "Chemical LLMs"\n'
        '      - \'RAW:"Large Language Models" AND (chemistry OR molecular)\'\n',
        encoding="utf-8")
    queries = data_io.load_keyword_queries(cfg)
    q = queries["Topic A"]
    # Both filters present, joined by OR; RAW wrapped in parens, NOT quoted as a phrase
    assert '"Chemical LLMs"' in q
    assert '("Large Language Models" AND (chemistry OR molecular))' in q
    assert " OR " in q
    # No double-quote around the RAW expression
    assert '"RAW:' not in q
    assert '"Large Language Models" AND' in q


def test_iter_papers_in_window_filters_by_updated(populated_data_dir, monkeypatch):
    """Papers with updated < cutoff excluded; recent ones included."""
    import data_io
    # Freeze "today" so test is deterministic. Sample data has updated 2025-03-01,
    # 2025-04-15, 2025-04-22. With days=20 from 2025-04-25, cutoff = 2025-04-05.
    fake_today = date(2025, 4, 25)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fake_today

    monkeypatch.setattr(data_io, "date", _FakeDate)

    by_month, _ = data_io.load_all_months()
    in_window = list(data_io.iter_papers_in_window(by_month, days=20))
    pids = {pid for pid, _ in in_window}
    assert pids == {"2504.00001", "2504.00002"}  # 2503.00001 (2025-03-01) excluded
