"""Tests for tools/retag_corpus.py — apply canonical tags to existing corpus."""
import json
import sys
import textwrap

import pytest


@pytest.fixture
def canonical_path(tmp_path):
    yaml_text = textwrap.dedent("""\
        dft:
          group: methods
          synonyms: [dft, density functional theory]
        gnn:
          group: architectures
          synonyms: [graph neural networks]
    """)
    p = tmp_path / "canonical.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return p


def _setup_paper(populated_data_dir, abstract, existing_tags=None):
    import data_io
    by_month, _ = data_io.load_all_months()
    by_month["2025-04"]["2504.00001"]["abstract"] = abstract
    by_month["2025-04"]["2504.00001"]["tags"] = existing_tags or []
    data_io.save_month(by_month, "2025-04")


def test_retag_paper_adds_missing_tags(populated_data_dir, canonical_path):
    """Paper without tags but with chem terms in abstract gets tagged."""
    import retag_corpus
    _setup_paper(populated_data_dir, "We use DFT and graph neural networks for chemistry.")
    stats = retag_corpus.run(canonical_path)
    import data_io
    by_month, _ = data_io.load_all_months()
    rec = by_month["2025-04"]["2504.00001"]
    assert sorted(rec["tags"]) == ["dft", "gnn"]


def test_retag_paper_no_change_when_already_tagged(populated_data_dir, canonical_path):
    """Re-running retag is idempotent: paper already has correct tags → no change."""
    import retag_corpus
    _setup_paper(populated_data_dir,
                 "We use DFT and graph neural networks for chemistry.",
                 existing_tags=["dft", "gnn"])
    stats = retag_corpus.run(canonical_path)
    assert stats["unchanged"] >= 1
    assert stats["changed"] == 0


def test_retag_paper_replaces_stale_tags(populated_data_dir, canonical_path):
    """If canonical changed, old tags get replaced with current matches."""
    import retag_corpus
    _setup_paper(populated_data_dir,
                 "We use DFT calculations only.",
                 existing_tags=["gnn", "old-stale-tag"])
    retag_corpus.run(canonical_path)
    import data_io
    by_month, _ = data_io.load_all_months()
    rec = by_month["2025-04"]["2504.00001"]
    # 'gnn' and 'old-stale-tag' shouldn't be in result; 'dft' should
    assert rec["tags"] == ["dft"]


def test_retag_paper_empty_abstract_clears_tags(populated_data_dir, canonical_path):
    """Empty abstract → empty tag list (no false positives)."""
    import retag_corpus
    _setup_paper(populated_data_dir, "", existing_tags=["dft"])
    retag_corpus.run(canonical_path)
    import data_io
    by_month, _ = data_io.load_all_months()
    rec = by_month["2025-04"]["2504.00001"]
    assert rec["tags"] == []


def test_retag_corpus_returns_stats(populated_data_dir, canonical_path):
    """run() returns dict with changed/unchanged/total counts."""
    import retag_corpus
    _setup_paper(populated_data_dir, "We use DFT and graph neural networks.")
    stats = retag_corpus.run(canonical_path)
    assert "changed" in stats
    assert "unchanged" in stats
    assert "total" in stats
    assert stats["changed"] + stats["unchanged"] == stats["total"]


def test_retag_corpus_rerenders_abstracts(populated_data_dir, canonical_path):
    """After retag, abstract .md files are regenerated to reflect new tags
    (frontmatter `tags:`) and apply linkify_urls fix."""
    import retag_corpus
    _setup_paper(populated_data_dir,
                 "We use DFT, code at https://github.com/foo/bar here.")
    retag_corpus.run(canonical_path)
    import data_io
    by_month, _ = data_io.load_all_months()
    rec = by_month["2025-04"]["2504.00001"]
    abs_path = data_io.abstract_path("2504.00001", rec)
    assert abs_path.exists()
    md = abs_path.read_text(encoding="utf-8")
    # Frontmatter has the new tag
    assert "dft" in md
    # URL was linkified
    assert "[https://github.com/foo/bar](https://github.com/foo/bar)" in md
