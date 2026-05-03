"""Tests for tools/tag_analysis.py — Phase 2 candidate keyword extraction."""
import json

import pytest


@pytest.fixture
def synthetic_corpus():
    """Tiny corpus with intentional topical bias to assert against."""
    return [
        "Density functional theory DFT calculations of crystal structures.",
        "DFT based electronic structure calculations using ab initio methods.",
        "Machine learning force fields trained on DFT data for molecular dynamics.",
        "Graph neural networks for molecular property prediction.",
        "GNN architectures for chemistry message passing and attention.",
        "Equivariant graph neural networks for 3D molecular representations.",
    ]


def test_clean_abstract_strips_urls():
    """URLs (http/https/www) are removed, surrounding text preserved."""
    import tag_analysis
    text = "We use diffusion models. See https://github.com/foo/bar for code."
    cleaned = tag_analysis.clean_abstract(text)
    assert "https" not in cleaned
    assert "github.com" not in cleaned
    assert "diffusion models" in cleaned
    assert "for code" in cleaned


def test_clean_abstract_strips_arxiv_ids():
    """Bare arxiv IDs like 2503.12345 / 2503.12345v2 are removed."""
    import tag_analysis
    text = "Following 2503.12345v2 we extend the work in 2401.99999."
    cleaned = tag_analysis.clean_abstract(text)
    assert "2503.12345" not in cleaned
    assert "2401.99999" not in cleaned
    assert "extend the work" in cleaned


def test_clean_abstract_preserves_chemistry_terms():
    """Domain-relevant text passes through untouched."""
    import tag_analysis
    text = "DFT calculations of NMC cathode using GPAW + U=3eV correction."
    cleaned = tag_analysis.clean_abstract(text)
    assert "DFT" in cleaned
    assert "NMC cathode" in cleaned
    assert "GPAW" in cleaned


def test_clean_abstract_collapses_whitespace():
    """Multi-space gaps left by stripped URLs collapse to single space."""
    import tag_analysis
    text = "before  https://x.com/y  after"
    cleaned = tag_analysis.clean_abstract(text)
    assert "  " not in cleaned
    assert cleaned == "before after"


def test_collect_corpus_applies_cleaning(populated_data_dir):
    """collect_corpus runs clean_abstract on every paper, so URLs disappear."""
    import tag_analysis
    import data_io
    by_month, _ = data_io.load_all_months()
    by_month["2025-04"]["2504.99999"] = {
        **by_month["2025-04"]["2504.00001"],
        "abstract": "Method described at https://github.com/test here.",
    }
    docs = tag_analysis.collect_corpus(by_month)
    assert all("https" not in d for d in docs)
    assert any("Method described" in d for d in docs)


def test_domain_stopwords_includes_paper_boilerplate():
    """Common paper boilerplate words are in DOMAIN_STOPWORDS."""
    import tag_analysis
    for word in ("propose", "approach", "method", "framework",
                 "results", "demonstrate", "novel"):
        assert word in tag_analysis.DOMAIN_STOPWORDS


def test_extract_tfidf_filters_domain_stopwords():
    """Domain stopwords like 'propose'/'approach' don't appear in top candidates."""
    import tag_analysis
    # Corpus where every doc uses generic ML-paper boilerplate
    docs = [
        "We propose a novel approach to graph neural networks.",
        "We propose a novel method for diffusion models.",
        "We propose a novel framework for retrosynthesis.",
        "We demonstrate results showing graph neural networks improve performance.",
        "We demonstrate results showing diffusion models achieve state of the art.",
    ]
    pairs = tag_analysis.extract_tfidf(docs, top_n=20)
    terms = {t.lower() for t, _ in pairs}
    for blocked in ("propose", "novel", "approach", "method",
                    "framework", "demonstrate", "results"):
        for term in terms:
            assert blocked not in term.split(), \
                f"domain stopword {blocked!r} leaked into term {term!r}"


def test_extract_tfidf_default_is_multiword():
    """By default, TF-IDF returns only bigrams/trigrams — no single-word noise."""
    import tag_analysis
    docs = [
        "We propose a novel approach to graph neural networks.",
        "Graph neural networks are powerful for molecular tasks.",
        "Diffusion models for molecular generation work well.",
        "Diffusion models outperform graph neural networks here.",
    ]
    pairs = tag_analysis.extract_tfidf(docs, top_n=20)
    for term, _ in pairs:
        assert " " in term, f"expected multi-word term, got {term!r}"


def test_collect_corpus_uses_abstract_field(populated_data_dir, sample_records):
    """collect_corpus yields the 'abstract' string from each paper record."""
    import tag_analysis
    import data_io
    by_month, _ = data_io.load_all_months()
    docs = tag_analysis.collect_corpus(by_month)
    assert len(docs) == len(sample_records)
    assert all(isinstance(d, str) for d in docs)


def test_collect_corpus_skips_empty_abstracts(populated_data_dir):
    """Papers without abstract content are filtered out."""
    import tag_analysis
    import data_io
    by_month, _ = data_io.load_all_months()
    by_month["2025-04"]["2504.99999"] = {
        **by_month["2025-04"]["2504.00001"],
        "abstract": "",
    }
    docs = tag_analysis.collect_corpus(by_month)
    assert "" not in docs


def test_extract_tfidf_returns_ranked_pairs(synthetic_corpus):
    """TF-IDF returns list[tuple[str, float]] sorted by score desc."""
    import tag_analysis
    pairs = tag_analysis.extract_tfidf(synthetic_corpus, top_n=20)
    assert pairs, "should produce candidates"
    assert all(isinstance(t, str) and isinstance(s, float) for t, s in pairs)
    scores = [s for _, s in pairs]
    assert scores == sorted(scores, reverse=True), "must be sorted desc"


def test_extract_tfidf_filters_stopwords(synthetic_corpus):
    """Common English stopwords are excluded from top candidates."""
    import tag_analysis
    pairs = tag_analysis.extract_tfidf(synthetic_corpus, top_n=20)
    terms = {t.lower() for t, _ in pairs}
    for stop in ("the", "and", "of", "a", "in", "for"):
        assert stop not in terms, f"stopword {stop!r} leaked into candidates"


def test_extract_tfidf_top_n_caps_output(synthetic_corpus):
    """top_n parameter truncates the result list."""
    import tag_analysis
    pairs = tag_analysis.extract_tfidf(synthetic_corpus, top_n=5)
    assert len(pairs) <= 5


def test_extract_yake_runs_and_returns_pairs(synthetic_corpus):
    """YAKE produces ranked (term, score) pairs for the synthetic corpus."""
    import tag_analysis
    pairs = tag_analysis.extract_yake(synthetic_corpus, top_n=20)
    assert pairs
    assert all(isinstance(t, str) and isinstance(s, float) for t, s in pairs)


def test_write_candidates_creates_per_algo_json(tmp_path):
    """write_candidates emits one JSON file per algorithm with schema [{term, score}, ...]."""
    import tag_analysis
    results = {
        "tfidf": [("dft", 1.5), ("gnn", 1.2)],
        "yake": [("density functional", 0.8)],
    }
    tag_analysis.write_candidates(results, tmp_path)
    data = json.loads((tmp_path / "candidates_tfidf.json").read_text(encoding="utf-8"))
    assert data == [{"term": "dft", "score": 1.5}, {"term": "gnn", "score": 1.2}]
    data2 = json.loads((tmp_path / "candidates_yake.json").read_text(encoding="utf-8"))
    assert data2 == [{"term": "density functional", "score": 0.8}]


def test_write_comparison_groups_terms_by_overlap_count(tmp_path):
    """Terms found in N algorithms are grouped under '## Found in N algorithm(s)'."""
    import tag_analysis
    results = {
        "tfidf": [("dft", 1.0), ("gnn", 1.0), ("ml", 1.0)],
        "yake": [("dft", 0.5), ("gnn", 0.5), ("retrosynthesis", 0.5)],
    }
    out = tmp_path / "comparison.md"
    tag_analysis.write_comparison(results, out)
    content = out.read_text(encoding="utf-8")
    # dft + gnn in both algos; ml + retrosynthesis in one each
    assert "Found in 2 algorithm(s)" in content
    assert "Found in 1 algorithm(s)" in content
    for term in ("dft", "gnn", "ml", "retrosynthesis"):
        assert term in content


def test_write_comparison_term_matching_is_case_insensitive(tmp_path):
    """'DFT' and 'dft' from different algorithms count as the same term."""
    import tag_analysis
    results = {
        "tfidf": [("DFT", 1.0)],
        "yake": [("dft", 0.5)],
    }
    out = tmp_path / "comparison.md"
    tag_analysis.write_comparison(results, out)
    content = out.read_text(encoding="utf-8")
    assert "Found in 2 algorithm(s)" in content
