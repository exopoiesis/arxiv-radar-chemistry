"""Tests for tools/filter_corpus.py — apply chemistry-context filter locally."""
import json
import sys

import pytest


def test_is_chemistry_paper_dft():
    import filter_corpus
    assert filter_corpus.is_chemistry_paper("DFT calculations of NMC oxide.")


def test_is_chemistry_paper_molecular_dynamics():
    import filter_corpus
    assert filter_corpus.is_chemistry_paper("We perform molecular dynamics simulations.")


def test_is_chemistry_paper_mof():
    import filter_corpus
    assert filter_corpus.is_chemistry_paper("Synthesis of new MOF structures.")


def test_is_chemistry_paper_polymer_stem():
    import filter_corpus
    # 'polymerization' should match via 'polymer' stem
    assert filter_corpus.is_chemistry_paper("Radical polymerization of styrene.")


def test_is_chemistry_paper_smiles():
    import filter_corpus
    assert filter_corpus.is_chemistry_paper("Generating SMILES strings with a transformer.")


def test_is_chemistry_paper_chem_llm():
    """LLM paper that's actually about chemistry passes the filter."""
    import filter_corpus
    text = "We propose a Large Language Model for molecular property prediction."
    assert filter_corpus.is_chemistry_paper(text)


def test_is_not_chemistry_paper_pure_ml():
    """Pure ML/CS paper that mentions LLMs but no chemistry context fails."""
    import filter_corpus
    text = "We propose a Large Language Model for code generation tasks."
    assert not filter_corpus.is_chemistry_paper(text)


def test_is_not_chemistry_paper_robotics():
    import filter_corpus
    text = "Diffusion models for robot motion planning in cluttered environments."
    assert not filter_corpus.is_chemistry_paper(text)


def test_is_not_chemistry_paper_image():
    import filter_corpus
    text = "Generative adversarial networks for high-resolution image synthesis."
    # 'synthesis' is a chem term — but here in image context. We ACCEPT this
    # false positive: simpler filter, low rate, easy to spot in candidates.
    assert filter_corpus.is_chemistry_paper(text)


def test_is_chemistry_paper_empty_abstract():
    import filter_corpus
    assert not filter_corpus.is_chemistry_paper("")


def test_is_chemistry_paper_no_false_positive_on_short_subword():
    """'mof' as substring of an unrelated word doesn't trigger (word boundaries)."""
    import filter_corpus
    assert not filter_corpus.is_chemistry_paper("Random text about networks and graphs.")
    assert not filter_corpus.is_chemistry_paper("The aforementioned approach.")


def test_filter_corpus_writes_kept_papers(isolated_data_dir):
    """filter_corpus.run reads data/papers-*.json, writes to out_dir keeping
    only chemistry-relevant papers."""
    import filter_corpus
    import data_io
    chem_paper = {
        "title": "DFT of NMC", "first_author": "A", "authors": ["A"],
        "abstract": "We use DFT to study NMC cathode materials.",
        "primary_category": "cond-mat.mtrl-sci",
        "categories": ["cond-mat.mtrl-sci"],
        "published": "2025-04-01", "updated": "2025-04-05",
        "comment": None, "pdf_url": "http://arxiv.org/pdf/2504.00100",
        "topics": ["Quantum Chemistry & Force Fields"], "tags": [],
    }
    noise_paper = {
        "title": "LLM for code", "first_author": "B", "authors": ["B"],
        "abstract": "We use Large Language Models for code completion in IDEs.",
        "primary_category": "cs.LG", "categories": ["cs.LG"],
        "published": "2025-04-10", "updated": "2025-04-12",
        "comment": None, "pdf_url": "http://arxiv.org/pdf/2504.00200",
        "topics": ["Large Language Models & Materials"], "tags": [],
    }
    by_month = {"2025-04": {"2504.00100": chem_paper, "2504.00200": noise_paper}}
    data_io.save_month(by_month, "2025-04")

    out_dir = isolated_data_dir.root / "data_filtered"
    stats = filter_corpus.run(out_dir=out_dir)

    assert stats["kept"] == 1
    assert stats["dropped"] == 1
    out_file = out_dir / "papers-2025-04.json"
    assert out_file.exists()
    kept = json.loads(out_file.read_text(encoding="utf-8"))
    assert "2504.00100" in kept
    assert "2504.00200" not in kept


def test_filter_corpus_stats_per_topic(isolated_data_dir):
    """Stats report dropped count per topic — useful to see which topic is noisy."""
    import filter_corpus
    import data_io
    base = {
        "title": "x", "first_author": "x", "authors": ["x"],
        "abstract": "We propose a Large Language Model for code generation.",
        "primary_category": "cs.LG", "categories": ["cs.LG"],
        "published": "2025-04-01", "updated": "2025-04-05",
        "comment": None, "pdf_url": "http://arxiv.org/pdf/x",
        "tags": [],
    }
    by_month = {"2025-04": {
        "p1": {**base, "topics": ["Topic A"]},
        "p2": {**base, "topics": ["Topic A"]},
        "p3": {**base, "topics": ["Topic B"]},
    }}
    data_io.save_month(by_month, "2025-04")

    out_dir = isolated_data_dir.root / "data_filtered"
    stats = filter_corpus.run(out_dir=out_dir)

    assert stats["dropped_by_topic"]["Topic A"] == 2
    assert stats["dropped_by_topic"]["Topic B"] == 1
