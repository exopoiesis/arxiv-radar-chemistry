"""Tests for tools/archive_old.py — prune old shards + orphan HTML sweep."""
import json
from datetime import date

import pytest


@pytest.fixture
def fake_today(monkeypatch):
    """Freeze today to 2026-04-26."""
    import archive_old
    fixed = date(2026, 4, 26)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fixed
    monkeypatch.setattr(archive_old, "date", _FakeDate)
    return fixed


@pytest.fixture
def multi_month_corpus(isolated_data_dir):
    """Shards spanning the 2-year boundary from today=2026-04-26.

    2024-03 → ends Mar 31 2024, fully older than cutoff (Apr 26 2024) → prune
    2024-04 → ends Apr 30 2024, next-month start May 1 2024 > cutoff → keep
    2025-06 → recent → keep
    2026-04 → current → keep
    """
    import data_io
    base = {"first_author": "A", "authors": ["A"], "abstract": "DFT calc.",
            "primary_category": "cond-mat.mtrl-sci",
            "categories": ["cond-mat.mtrl-sci"],
            "comment": None, "pdf_url": "http://arxiv.org/pdf/x",
            "topics": [], "tags": []}
    by_month = {
        "2024-03": {"2403.00001": {**base, "title": "old", "published": "2024-03-15", "updated": "2024-03-15"}},
        "2024-04": {"2404.00001": {**base, "title": "border", "published": "2024-04-15", "updated": "2024-04-15"}},
        "2025-06": {"2506.00001": {**base, "title": "mid", "published": "2025-06-15", "updated": "2025-06-15"}},
        "2026-04": {"2604.00001": {**base, "title": "now", "published": "2026-04-15", "updated": "2026-04-15"}},
    }
    for month, papers in by_month.items():
        data_io.save_month(by_month, month)
    # Plant HTML fragments for every paper to mirror real-pipeline state
    for papers in by_month.values():
        for pid in papers:
            (data_io.DOCS_ABSTRACTS_DIR / f"{pid}.html").write_text(
                f"<article>{pid}</article>", encoding="utf-8")
    return isolated_data_dir


def test_prunes_old_shard(multi_month_corpus, fake_today):
    """A shard older than threshold is removed from data/."""
    import archive_old
    stats = archive_old.run(threshold_days=730)
    assert "2024-03" in stats["deleted_shards"]
    assert not (multi_month_corpus.data / "papers-2024-03.json").exists()


def test_keeps_recent_shards(multi_month_corpus, fake_today):
    """Border + recent shards stay in data/."""
    import archive_old
    archive_old.run(threshold_days=730)
    for m in ("2024-04", "2025-06", "2026-04"):
        assert (multi_month_corpus.data / f"papers-{m}.json").exists(), m


def test_deletes_html_for_pruned_papers(multi_month_corpus, fake_today):
    """When 2024-03 shard is pruned, docs/abstracts/<pid>.html for those
    papers must also disappear."""
    import archive_old
    pid_old = "2403.00001"
    pid_kept = "2506.00001"
    assert (multi_month_corpus.docs_abstracts / f"{pid_old}.html").exists()
    archive_old.run(threshold_days=730)
    assert not (multi_month_corpus.docs_abstracts / f"{pid_old}.html").exists()
    assert (multi_month_corpus.docs_abstracts / f"{pid_kept}.html").exists()


def test_orphan_html_swept(multi_month_corpus, fake_today):
    """An HTML file whose pid isn't in any current shard is removed.

    Simulates leftover state from earlier archive operations or hand edits.
    """
    import archive_old
    orphan = multi_month_corpus.docs_abstracts / "9999.99999.html"
    orphan.write_text("<article>orphan</article>", encoding="utf-8")
    stats = archive_old.run(threshold_days=730)
    assert not orphan.exists()
    assert stats["orphan_html"] >= 1


def test_idempotent(multi_month_corpus, fake_today):
    """Second run is a no-op on a clean state."""
    import archive_old
    s1 = archive_old.run(threshold_days=730)
    s2 = archive_old.run(threshold_days=730)
    assert s1["deleted_shards"] == ["2024-03"]
    assert s2["deleted_shards"] == []
    assert s2["html_deleted_with_shards"] == 0


def test_threshold_one_year(multi_month_corpus, fake_today):
    """With threshold=365, both 2024-03 and 2024-04 shards are pruned."""
    import archive_old
    stats = archive_old.run(threshold_days=365)
    assert set(stats["deleted_shards"]) == {"2024-03", "2024-04"}
    assert (multi_month_corpus.data / "papers-2025-06.json").exists()
