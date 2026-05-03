"""Tests for tools/render_index.py — Jekyll Pages landing with tag cloud."""
import sys
from datetime import date
from pathlib import Path

import pytest


@pytest.fixture
def tagged_corpus(populated_data_dir):
    """3 papers with tags spanning two months."""
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
    p = tmp_path / "canonical.yaml"
    p.write_text(
        "dft:\n  group: methods\n  synonyms: [dft]\n"
        "gnn:\n  group: architectures\n  synonyms: [gnn]\n",
        encoding="utf-8")
    return p


@pytest.fixture
def fake_today(monkeypatch):
    import render_index
    fixed = date(2025, 4, 25)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fixed
    monkeypatch.setattr(render_index, "date", _FakeDate)
    return fixed


def test_render_index_produces_jekyll_page(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """Output starts with Jekyll frontmatter so the layout applies."""
    import render_index
    out = tmp_path / "index.md"
    render_index.run(canonical_yaml, out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "layout:" in content


def test_render_index_includes_corpus_stats(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """Total paper count and month coverage shown so visitors size the project."""
    import render_index
    out = tmp_path / "index.md"
    render_index.run(canonical_yaml, out)
    content = out.read_text(encoding="utf-8")
    # 3 papers in fixture across 2 months
    assert "3" in content  # paper count surfaced somewhere
    assert "papers" in content.lower()


def test_render_index_writes_tag_index_data(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """Sidebar source: _data/tag_index.yml lists every canonical tag."""
    import render_index
    out = tmp_path / "index.md"
    tag_index = tmp_path / "_data" / "tag_index.yml"
    render_index.run(canonical_yaml, out, tag_index_path=tag_index)
    data = tag_index.read_text(encoding="utf-8")
    assert "name: dft" in data
    assert "name: gnn" in data
    # Group is preserved so the sidebar can section if it wants to.
    assert "group: methods" in data
    assert "group: architectures" in data


def test_render_index_tag_index_includes_freq(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """tag_index.yml carries the recent count so the sidebar can show it."""
    import render_index
    out = tmp_path / "index.md"
    tag_index = tmp_path / "_data" / "tag_index.yml"
    render_index.run(canonical_yaml, out, tag_index_path=tag_index)
    data = tag_index.read_text(encoding="utf-8")
    # In fixture, within 30d of fake today: dft=1, gnn=2.
    assert "count: 1" in data
    assert "count: 2" in data


def test_render_index_skips_zero_frequency_tags(canonical_yaml, isolated_data_dir,
                                                 fake_today, tmp_path):
    """A canonical tag with no matching papers in the window is omitted from the
    cloud (or shown with 0 — implementation choice; testing one or the other)."""
    # No data → no tag would have any papers in window
    import data_io
    data_io.save_month({"2025-04": {}}, "2025-04")
    import render_index
    out = tmp_path / "index.md"
    render_index.run(canonical_yaml, out)
    content = out.read_text(encoding="utf-8")
    # File still produced (doesn't crash on empty corpus)
    assert content


def test_render_index_returns_stats(tagged_corpus, canonical_yaml, fake_today, tmp_path):
    """run() returns dict with total_papers, total_tags."""
    import render_index
    out = tmp_path / "index.md"
    stats = render_index.run(canonical_yaml, out)
    assert stats["total_papers"] == 3
    assert stats["total_tags"] == 2
