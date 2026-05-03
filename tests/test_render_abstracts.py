"""Tests for tools/render_abstracts.py — batch generation of abstract files."""
import sys


def _run_render_abstracts(force=False, include_md=False):
    import render_abstracts
    saved_argv = sys.argv
    argv = ["render_abstracts.py"]
    if force: argv.append("--force")
    if include_md: argv.append("--include-md")
    sys.argv = argv
    try:
        render_abstracts.main()
    finally:
        sys.argv = saved_argv


def test_render_abstracts_writes_html_fragments(populated_data_dir):
    """Default: every paper gets a docs/abstracts/<pid>.html fragment."""
    _run_render_abstracts()
    assert (populated_data_dir.docs_abstracts / "2503.00001.html").exists()
    assert (populated_data_dir.docs_abstracts / "2504.00001.html").exists()
    assert (populated_data_dir.docs_abstracts / "2504.00002.html").exists()


def test_render_abstracts_default_skips_md(populated_data_dir):
    """Default no longer writes the legacy markdown — that's render_readme's job."""
    _run_render_abstracts()
    assert not (populated_data_dir.abstracts / "2503.00001.md").exists()


def test_render_abstracts_include_md_writes_both(populated_data_dir):
    """--include-md restores the legacy md output (for ad-hoc backfills)."""
    _run_render_abstracts(include_md=True)
    assert (populated_data_dir.docs_abstracts / "2503.00001.html").exists()
    assert (populated_data_dir.abstracts / "2503.00001.md").exists()


def test_render_abstracts_idempotent(populated_data_dir):
    """Second run doesn't rewrite existing HTML files."""
    _run_render_abstracts()
    target = populated_data_dir.docs_abstracts / "2503.00001.html"
    target.write_text("MUTATED", encoding="utf-8")
    _run_render_abstracts()
    assert target.read_text(encoding="utf-8") == "MUTATED"


def test_render_abstracts_force_rewrites(populated_data_dir):
    """--force regenerates HTML even if it already exists."""
    _run_render_abstracts()
    target = populated_data_dir.docs_abstracts / "2503.00001.html"
    target.write_text("MUTATED", encoding="utf-8")
    _run_render_abstracts(force=True)
    assert target.read_text(encoding="utf-8") != "MUTATED"
    assert "Old paper" in target.read_text(encoding="utf-8")
