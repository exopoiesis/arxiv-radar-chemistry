"""Tests for tools/tag_matcher.py — match canonical tags from abstract text."""
import textwrap

import pytest


@pytest.fixture
def sample_canonical(tmp_path):
    """Tiny canonical.yaml with a few representative tags."""
    yaml_text = textwrap.dedent("""\
        dft:
          group: methods
          synonyms: [dft, density functional theory, density functional]
        gnn:
          group: architectures
          synonyms: [graph neural networks, graph neural network, gnns]
        chemical-llm:
          group: llm
          synonyms: [chemical llms, chemical language models]
        multimodal-llm:
          group: llm
          synonyms: [multimodal large language, vision language models]
    """)
    p = tmp_path / "canonical.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return p


def test_load_canonical_tags(sample_canonical):
    """Returns dict mapping canonical name → metadata with group + synonyms."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    assert set(canonical.keys()) == {"dft", "gnn", "chemical-llm", "multimodal-llm"}
    assert canonical["dft"]["group"] == "methods"
    assert "density functional theory" in canonical["dft"]["synonyms"]


def test_match_tags_single_synonym(sample_canonical):
    """Abstract mentioning one synonym gets the canonical name."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    tags = tag_matcher.match_tags("We use DFT to study NMC.", matchers)
    assert tags == ["dft"]


def test_match_tags_multi(sample_canonical):
    """Abstract with multiple chem terms gets all matching canonical tags."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    tags = tag_matcher.match_tags(
        "We combine DFT calculations with graph neural networks.", matchers)
    assert sorted(tags) == ["dft", "gnn"]


def test_match_tags_returns_sorted(sample_canonical):
    """Output is alphabetically sorted for stable diffs."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    tags = tag_matcher.match_tags(
        "graph neural networks then DFT then chemical language models", matchers)
    assert tags == sorted(tags)


def test_match_tags_case_insensitive(sample_canonical):
    """Synonyms match regardless of abstract casing."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    assert "dft" in tag_matcher.match_tags("DENSITY FUNCTIONAL THEORY rules", matchers)
    assert "dft" in tag_matcher.match_tags("density functional theory ok", matchers)


def test_match_tags_word_boundary(sample_canonical):
    """'dft' doesn't match inside an unrelated word like 'softdft'."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    tags = tag_matcher.match_tags("Look at softdft for fun.", matchers)
    assert "dft" not in tags


def test_match_tags_no_match(sample_canonical):
    """Empty list when no synonym hits."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    assert tag_matcher.match_tags("Random text about robots.", matchers) == []


def test_match_tags_empty_abstract(sample_canonical):
    """Empty abstract → empty tag list."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    assert tag_matcher.match_tags("", matchers) == []


def test_match_tags_multimodal_llm(sample_canonical):
    """Multi-word synonyms with hyphens and spaces work."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    assert "multimodal-llm" in tag_matcher.match_tags(
        "We propose a multimodal large language framework.", matchers)


def test_match_tags_one_synonym_enough_for_tag(sample_canonical):
    """Hitting any one synonym is enough; we don't require all of them."""
    import tag_matcher
    canonical = tag_matcher.load_canonical_tags(sample_canonical)
    matchers = tag_matcher.build_matchers(canonical)
    # Has 'gnns' acronym only, not the long form
    assert "gnn" in tag_matcher.match_tags("We use GNNs for chemistry.", matchers)
