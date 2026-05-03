"""Tests for tools/split_by_month.py — critically, the merge bug we hit before.

The original implementation REPLACED existing month files entirely, which
silently destroyed previously backfilled data when a second backfill produced
an overlapping monolith. The fixed version MUST merge.
"""
import json
import sys


def _run_split(source_path, delete_source=False):
    import split_by_month
    saved_argv = sys.argv
    args = ["split_by_month.py", "--source", str(source_path)]
    if delete_source:
        args.append("--delete-source")
    sys.argv = args
    try:
        return split_by_month.main()
    finally:
        sys.argv = saved_argv


def _write_monolith(path, papers):
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")


def test_split_creates_monthly_files(isolated_data_dir, sample_records):
    """Fresh run with no existing month files writes them by `updated` month."""
    monolith = isolated_data_dir.data / "papers.json"
    _write_monolith(monolith, sample_records)
    rc = _run_split(monolith)
    assert rc == 0
    assert (isolated_data_dir.data / "papers-2025-03.json").exists()
    assert (isolated_data_dir.data / "papers-2025-04.json").exists()
    march = json.loads((isolated_data_dir.data / "papers-2025-03.json").read_text(encoding="utf-8"))
    assert "2503.00001" in march
    assert len(march) == 1
    april = json.loads((isolated_data_dir.data / "papers-2025-04.json").read_text(encoding="utf-8"))
    assert {"2504.00001", "2504.00002"} == set(april.keys())


def test_split_merges_into_existing_files(isolated_data_dir):
    """The bug we hit: split must MERGE with existing month files, not replace.

    Setup: papers-2025-04.json already has paper P1.
    Action: split a monolith containing paper P2 (also updated 2025-04).
    Expected: papers-2025-04.json now has BOTH P1 and P2.
    """
    p1 = {
        "title": "Pre-existing paper", "first_author": "X", "authors": ["X"],
        "abstract": "abs", "primary_category": "cs.LG", "categories": ["cs.LG"],
        "published": "2025-04-01", "updated": "2025-04-05", "comment": None,
        "pdf_url": "http://arxiv.org/pdf/2504.00100",
        "topics": ["Topic A"], "tags": [],
    }
    p2 = {
        "title": "Newly fetched paper", "first_author": "Y", "authors": ["Y"],
        "abstract": "abs", "primary_category": "cs.LG", "categories": ["cs.LG"],
        "published": "2025-04-10", "updated": "2025-04-15", "comment": None,
        "pdf_url": "http://arxiv.org/pdf/2504.00200",
        "topics": ["Topic B"], "tags": [],
    }
    existing = isolated_data_dir.data / "papers-2025-04.json"
    existing.write_text(json.dumps({"2504.00100": p1}, ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")

    monolith = isolated_data_dir.data / "papers.json"
    _write_monolith(monolith, {"2504.00200": p2})
    rc = _run_split(monolith)
    assert rc == 0

    merged = json.loads(existing.read_text(encoding="utf-8"))
    assert "2504.00100" in merged, "pre-existing paper must survive"
    assert "2504.00200" in merged, "new paper must be added"
    assert merged["2504.00100"]["title"] == "Pre-existing paper"


def test_split_merges_topics_when_id_collides(isolated_data_dir):
    """If both old and new have same arxiv_id but different topics → union of topics."""
    pid = "2504.00100"
    old = {
        "title": "Same paper", "first_author": "X", "authors": ["X"],
        "abstract": "abs", "primary_category": "cs.LG", "categories": ["cs.LG"],
        "published": "2025-04-01", "updated": "2025-04-05", "comment": None,
        "pdf_url": "http://arxiv.org/pdf/2504.00100",
        "topics": ["Topic A"], "tags": [],
    }
    new = dict(old)
    new["topics"] = ["Topic B"]

    existing = isolated_data_dir.data / "papers-2025-04.json"
    existing.write_text(json.dumps({pid: old}, ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")
    monolith = isolated_data_dir.data / "papers.json"
    _write_monolith(monolith, {pid: new})
    rc = _run_split(monolith)
    assert rc == 0

    merged = json.loads(existing.read_text(encoding="utf-8"))
    assert sorted(merged[pid]["topics"]) == ["Topic A", "Topic B"]


def test_split_delete_source_removes_monolith(isolated_data_dir, sample_records):
    """--delete-source removes the source file after successful split."""
    monolith = isolated_data_dir.data / "papers.json"
    _write_monolith(monolith, sample_records)
    _run_split(monolith, delete_source=True)
    assert not monolith.exists()
