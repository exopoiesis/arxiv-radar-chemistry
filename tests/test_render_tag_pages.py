"""Tests for tools/render_tag_pages.py — pre-generate Jekyll tag pages."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def tagged_corpus(populated_data_dir):
    """populated_data_dir + tags assigned for window/tag tests.

    3 papers in fixture:
      2503.00001 updated 2025-03-01 → tags=[dft]
      2504.00001 updated 2025-04-15 → tags=[dft, gnn]
      2504.00002 updated 2025-04-22 → tags=[gnn]
    """
    import data_io
    by_month, _ = data_io.load_all_months()
    by_month["2025-03"]["2503.00001"]["tags"] = ["dft"]
    by_month["2025-04"]["2504.00001"]["tags"] = ["dft", "gnn"]
    by_month["2025-04"]["2504.00002"]["tags"] = ["gnn"]
    data_io.save_month(by_month, "2025-03")
    data_io.save_month(by_month, "2025-04")
    return populated_data_dir


@pytest.fixture
def canonical_yaml(tmp_path):
    """Two canonical tags for testing."""
    p = tmp_path / "canonical.yaml"
    p.write_text(
        "dft:\n  group: methods\n  synonyms: [dft]\n"
        "gnn:\n  group: architectures\n  synonyms: [gnn]\n",
        encoding="utf-8")
    return p


@pytest.fixture
def fake_today(monkeypatch):
    """Freeze 'today' to 2025-04-25 for deterministic window filters."""
    import render_tag_pages
    fixed = date(2025, 4, 25)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fixed
    monkeypatch.setattr(render_tag_pages, "date", _FakeDate)
    return fixed


def test_render_tag_pages_creates_one_file_per_tag_per_window(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """For 2 tags × 5 windows = 10 files created."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    stats = render_tag_pages.run(canonical_yaml, out_dir)
    files = sorted(out_dir.glob("*.md"))
    assert len(files) == 2 * 5  # 2 tags, 5 windows


def test_tag_page_filters_by_tag(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """gnn page must list only papers with 'gnn' tag."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    gnn_all = (out_dir / "gnn-all.md").read_text(encoding="utf-8")
    assert "2504.00001" in gnn_all  # has 'gnn' tag
    assert "2504.00002" in gnn_all  # has 'gnn' tag
    assert "2503.00001" not in gnn_all  # has only 'dft', no 'gnn'


def test_tag_page_filters_by_window(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """7-day window from 2025-04-25 cuts off 2025-04-15 (10 days ago — within),
    excludes 2025-03-01 (older). 30-day window includes both."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    dft_7d = (out_dir / "dft-7d.md").read_text(encoding="utf-8")
    # 2503.00001 (March 1) is way outside 7-day window from April 25
    assert "2503.00001" not in dft_7d
    # 2504.00001 (April 15) is 10 days ago — outside 7-day window
    assert "2504.00001" not in dft_7d

    dft_30d = (out_dir / "dft-30d.md").read_text(encoding="utf-8")
    # 30-day window from April 25 starts March 26 — captures April 15
    assert "2504.00001" in dft_30d
    # 2503.00001 (March 1) still outside 30d
    assert "2503.00001" not in dft_30d

    dft_all = (out_dir / "dft-all.md").read_text(encoding="utf-8")
    # 'all' window has every paper with the tag
    assert "2503.00001" in dft_all
    assert "2504.00001" in dft_all


def test_tag_page_sorted_desc(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """Within a page, more recent papers appear first."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    dft_all = (out_dir / "dft-all.md").read_text(encoding="utf-8")
    pos_recent = dft_all.index("2504.00001")  # April 15
    pos_old = dft_all.index("2503.00001")  # March 1
    assert pos_recent < pos_old


def test_tag_page_has_window_navigation(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """Every tag page has links to other windows of the same tag."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    dft_30d = (out_dir / "dft-30d.md").read_text(encoding="utf-8")
    # navigation should mention all 5 windows
    for window in ("7d", "30d", "90d", "360d", "all"):
        assert window in dft_30d


def test_tag_page_uses_jekyll_layout(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """Each page starts with Jekyll frontmatter (layout: default)."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    page = (out_dir / "dft-30d.md").read_text(encoding="utf-8")
    assert page.startswith("---\n")
    assert "layout:" in page


def test_render_tag_pages_returns_stats(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """run() returns count of files written and entries per tag."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    stats = render_tag_pages.run(canonical_yaml, out_dir)
    assert stats["files_written"] == 10
    assert stats["tags"] == 2


def test_tag_page_per_paper_tags_use_current_window(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """Under each paper, its other tags link to the SAME window the user is on.

    Paper 2504.00001 (April 15) has tags [dft, gnn]. On dft-30d page, the
    paper-tags sub-line under its title should link to gnn-30d.html (same
    window). The current tag (dft) must be skipped — no self-links.
    """
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    dft_30d = (out_dir / "dft-30d.md").read_text(encoding="utf-8")
    assert 'href="gnn-30d.html"' in dft_30d
    assert 'class="paper-tags"' in dft_30d


def test_tag_page_title_is_popup_link(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """Each paper title is wrapped in <a class="abstract-popup"> pointing
    at /abstracts/<id>.html so the JS popup can intercept clicks."""
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    dft_all = (out_dir / "dft-all.md").read_text(encoding="utf-8")
    assert 'class="abstract-popup paper-title-link"' in dft_all
    assert 'href="../abstracts/2504.00001.html"' in dft_all


def test_tag_page_per_paper_tags_skip_self(
    tagged_corpus, canonical_yaml, fake_today, tmp_path
):
    """Inside paper-tags, the page's own tag is omitted (would be self-link)."""
    import re
    import render_tag_pages
    out_dir = tmp_path / "tag"
    render_tag_pages.run(canonical_yaml, out_dir)
    gnn_all = (out_dir / "gnn-all.md").read_text(encoding="utf-8")
    for m in re.finditer(r'<div class="paper-tags">.*?</div>', gnn_all, re.S):
        assert 'href="gnn-' not in m.group(0), (
            f"self-link found in paper-tags: {m.group(0)}")
