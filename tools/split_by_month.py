#!/usr/bin/env python3
"""Split a monolithic papers.json into monthly files data/papers-YYYY-MM.json.

Utility for one-shot conversion of legacy monolithic data (e.g. when adopting
this tooling in a fork that previously stored everything in one file). For
fresh fetches use backfill.py / daily_arxiv.py — they write monthly directly.

Sharding key is `updated` field (latest revision date) — aligns with arXiv
submittedDate semantics. Papers are stored as a flat dict by arxiv_id within
each monthly file. Existing month files are MERGED, never replaced.
"""
import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io

LOG = logging.getLogger("split")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None,
                        help="path to monolithic papers.json (default: <DATA_DIR>/papers.json)")
    parser.add_argument("--delete-source", action="store_true",
                        help="delete monolithic file after successful split")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    src = Path(args.source) if args.source else (data_io.DATA_DIR / "papers.json")
    LOG.info(f"loading {src} ({src.stat().st_size/1e6:.1f} MB)")
    with open(src, encoding="utf-8") as f:
        papers = json.load(f)
    LOG.info(f"source papers: {len(papers)}")

    incoming_by_month = defaultdict(dict)
    for pid, rec in papers.items():
        incoming_by_month[rec["updated"][:7]][pid] = rec

    by_month, _ = data_io.load_all_months()
    total_added = total_topic_merges = 0
    for month, new_papers in sorted(incoming_by_month.items()):
        existing = by_month.setdefault(month, {})
        added = 0
        for pid, rec in new_papers.items():
            if pid in existing:
                old_topics = set(existing[pid].get("topics", []))
                merged = old_topics | set(rec.get("topics", []))
                if merged != old_topics:
                    existing[pid]["topics"] = sorted(merged)
                    total_topic_merges += 1
            else:
                existing[pid] = rec
                added += 1
        data_io.save_month(by_month, month)
        LOG.info(f"  papers-{month}.json: total={len(existing):>5}, added={added:>4}")
        total_added += added

    grand_total = sum(len(m) for m in by_month.values())
    LOG.info(f"DONE. added={total_added} topic_merges={total_topic_merges} "
             f"grand_total={grand_total}")

    if args.delete_source:
        src.unlink()
        LOG.info(f"deleted {src}")
    else:
        LOG.info(f"source preserved at {src} (use --delete-source to remove)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
