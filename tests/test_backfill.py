"""Happy-path tests for tools/backfill.py helpers."""
import json
from datetime import date

import pytest


def test_month_shards_single_month():
    import backfill
    shards = list(backfill.month_shards(date(2025, 3, 15), date(2025, 3, 20)))
    assert shards == [(2025, 3)]


def test_month_shards_range():
    import backfill
    shards = list(backfill.month_shards(date(2025, 1, 1), date(2025, 4, 30)))
    assert shards == [(2025, 1), (2025, 2), (2025, 3), (2025, 4)]


def test_month_shards_year_rollover():
    import backfill
    shards = list(backfill.month_shards(date(2024, 11, 1), date(2025, 2, 1)))
    assert shards == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]


def test_shard_query_format():
    import backfill
    q = backfill.shard_query("foo OR bar", 2025, 3)
    assert "(foo OR bar)" in q
    assert "submittedDate:[202503010000 TO 202504010000]" in q


def test_shard_query_december_rollover():
    import backfill
    q = backfill.shard_query("foo", 2025, 12)
    assert "submittedDate:[202512010000 TO 202601010000]" in q


def test_load_keyword_queries(tmp_path, monkeypatch):
    """Reads config.yaml, multi-word filters get quoted, joined with ' OR '."""
    import backfill
    cfg_yaml = """
keywords:
  Topic A:
    filters: ["Graph Neural Networks", "GNN", "Geometric Deep Learning"]
  Topic B:
    filters: ["DFT"]
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_yaml, encoding="utf-8")
    monkeypatch.setattr(backfill, "CONFIG_FILE", cfg_path)

    queries = backfill.load_keyword_queries()
    assert set(queries.keys()) == {"Topic A", "Topic B"}
    assert '"Graph Neural Networks"' in queries["Topic A"]
    assert "GNN" in queries["Topic A"]  # single word, no quotes
    assert " OR " in queries["Topic A"]
    assert queries["Topic B"] == "DFT"


def test_checkpoint_roundtrip(isolated_data_dir, monkeypatch):
    """save_checkpoint then load_checkpoint returns the same set."""
    import backfill
    monkeypatch.setattr(backfill, "CHECKPOINT_FILE",
                        isolated_data_dir.data / "backfill_checkpoint.json")
    done = {"Topic A|2025-01", "Topic B|2025-02"}
    backfill.save_checkpoint(done)
    loaded = backfill.load_checkpoint()
    assert loaded == done


def test_checkpoint_missing_file_returns_empty(isolated_data_dir, monkeypatch):
    """No checkpoint file → empty set, no crash."""
    import backfill
    monkeypatch.setattr(backfill, "CHECKPOINT_FILE",
                        isolated_data_dir.data / "nonexistent.json")
    assert backfill.load_checkpoint() == set()
