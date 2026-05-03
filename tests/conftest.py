"""Shared pytest fixtures."""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))


@pytest.fixture
def sample_record():
    """A canonical paper record matching the schema in data_io.py."""
    return {
        "title": "Sample Paper on Graph Neural Networks",
        "first_author": "Alice Smith",
        "authors": ["Alice Smith", "Bob Jones"],
        "abstract": "We present a novel approach to GNN-based molecular property prediction.",
        "primary_category": "cs.LG",
        "categories": ["cs.LG", "physics.chem-ph"],
        "published": "2025-03-15",
        "updated": "2025-03-20",
        "comment": "10 pages, 4 figures",
        "pdf_url": "http://arxiv.org/pdf/2503.12345",
        "topics": ["Molecular Representation & Learning"],
        "tags": [],
    }


@pytest.fixture
def sample_records():
    """Three records spanning two months and varied topics, for filtering tests."""
    return {
        "2503.00001": {
            "title": "Old paper",
            "first_author": "A",
            "authors": ["A"],
            "abstract": "abs",
            "primary_category": "cs.LG",
            "categories": ["cs.LG"],
            "published": "2025-03-01",
            "updated": "2025-03-01",
            "comment": None,
            "pdf_url": "http://arxiv.org/pdf/2503.00001",
            "topics": ["Topic A"],
            "tags": [],
        },
        "2504.00001": {
            "title": "Recent paper in topic A",
            "first_author": "B",
            "authors": ["B"],
            "abstract": "abs",
            "primary_category": "cs.LG",
            "categories": ["cs.LG"],
            "published": "2025-04-10",
            "updated": "2025-04-15",
            "comment": None,
            "pdf_url": "http://arxiv.org/pdf/2504.00001",
            "topics": ["Topic A"],
            "tags": [],
        },
        "2504.00002": {
            "title": "Recent paper in topic B",
            "first_author": "C",
            "authors": ["C"],
            "abstract": "abs",
            "primary_category": "physics.chem-ph",
            "categories": ["physics.chem-ph"],
            "published": "2025-04-20",
            "updated": "2025-04-22",
            "comment": None,
            "pdf_url": "http://arxiv.org/pdf/2504.00002",
            "topics": ["Topic B"],
            "tags": [],
        },
    }


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path):
    """Redirect data_io DATA_DIR / ABSTRACTS_DIR / DOCS_ABSTRACTS_DIR to a
    temp path so tests never touch the real data/ folder."""
    import data_io
    data_dir = tmp_path / "data"
    abs_dir = tmp_path / "abstracts"
    docs_abs_dir = tmp_path / "docs" / "abstracts"
    data_dir.mkdir()
    abs_dir.mkdir()
    docs_abs_dir.mkdir(parents=True)
    monkeypatch.setattr(data_io, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_io, "ABSTRACTS_DIR", abs_dir)
    monkeypatch.setattr(data_io, "DOCS_ABSTRACTS_DIR", docs_abs_dir)

    # Tools that hard-code default output paths under data_io.ROOT need to be
    # re-pointed too — otherwise their default-path tests overwrite real
    # docs/_data/tag_index.yml etc.
    docs_data_dir = tmp_path / "docs" / "_data"
    docs_data_dir.mkdir(parents=True)
    try:
        import render_index
        monkeypatch.setattr(render_index, "DEFAULT_TAG_INDEX",
                            docs_data_dir / "tag_index.yml")
        monkeypatch.setattr(render_index, "DEFAULT_OUT",
                            tmp_path / "docs" / "index.md")
    except ImportError:
        pass
    return SimpleNamespace(root=tmp_path, data=data_dir,
                           abstracts=abs_dir, docs_abstracts=docs_abs_dir)


@pytest.fixture
def populated_data_dir(isolated_data_dir, sample_records):
    """Pre-populate isolated data/ with sample papers split by `updated` month."""
    by_month = {}
    for pid, rec in sample_records.items():
        m = rec["updated"][:7]
        by_month.setdefault(m, {})[pid] = rec
    for month, papers in by_month.items():
        path = isolated_data_dir.data / f"papers-{month}.json"
        path.write_text(json.dumps(papers, ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")
    return isolated_data_dir


def make_arxiv_result(arxiv_id="2503.12345v1", title="Test Paper",
                     authors=("A. Author", "B. Author"),
                     summary="Multi-line\nabstract here.",
                     primary_category="cs.LG",
                     categories=("cs.LG", "physics.chem-ph"),
                     published="2025-03-15", updated="2025-03-20",
                     comment=None):
    """Build a SimpleNamespace mimicking arxiv.Result for paper_to_record tests."""
    pub = datetime.fromisoformat(published).replace(tzinfo=timezone.utc)
    upd = datetime.fromisoformat(updated).replace(tzinfo=timezone.utc)
    author_objs = [SimpleNamespace(__str__=lambda self, n=name: n,
                                    name=name) for name in authors]
    # SimpleNamespace doesn't override __str__; wrap properly
    class _Author:
        def __init__(self, name): self.name = name
        def __str__(self): return self.name
    author_objs = [_Author(n) for n in authors]
    return SimpleNamespace(
        get_short_id=lambda: arxiv_id,
        title=title,
        authors=author_objs,
        summary=summary,
        primary_category=primary_category,
        categories=list(categories),
        published=pub,
        updated=upd,
        comment=comment,
    )


@pytest.fixture
def arxiv_result_factory():
    return make_arxiv_result
