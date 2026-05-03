#!/usr/bin/env python3
"""Prune corpus state: delete data shards older than threshold + orphan HTML.

What it does:
  1. Walk data/papers-YYYY-MM.json. For every shard whose month-end falls
     fully before today − threshold (default 2 years), load it, delete the
     corresponding docs/abstracts/<pid>.html for each paper inside, then
     delete the shard.
  2. Orphan-sweep: scan docs/abstracts/<pid>.html and delete any HTML whose
     pid no longer appears in the active corpus (catches inconsistencies
     left by earlier archive runs, partial failures, or hand edits).

No gzip, no /archive/ directory — just deletion. Authoritative copy of
abstract metadata lives on arxiv.org; we don't replicate it offline.

Idempotent: rerun any time. Used both by the monthly cron workflow and
manually after corpus surgery.
"""
import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io

LOG = logging.getLogger("archive_old")


def _next_month_first(year, month):
    """Date of the 1st of the month after (year, month)."""
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def _delete_html_for_pids(pids, docs_abstracts_dir):
    """Unlink docs/abstracts/<pid>.html for each pid; return count deleted."""
    deleted = 0
    for pid in pids:
        f = docs_abstracts_dir / f"{pid}.html"
        if f.exists():
            f.unlink()
            deleted += 1
    return deleted


def run(threshold_days=730):
    """Delete shards older than threshold_days; sweep orphan HTML.

    Returns a dict summary with shard / html / orphan counts.
    """
    cutoff = date.today() - timedelta(days=threshold_days)
    LOG.info(f"today={date.today()} cutoff={cutoff} (threshold={threshold_days}d)")

    deleted_shards = []
    html_deleted_with_shards = 0

    for f in sorted(data_io.DATA_DIR.glob("papers-*.json")):
        month_str = f.stem.replace("papers-", "")
        try:
            year, month = month_str.split("-")
            year, month = int(year), int(month)
        except ValueError:
            LOG.warning(f"skip non-month file: {f.name}")
            continue
        if _next_month_first(year, month) >= cutoff:
            continue
        with open(f, "r", encoding="utf-8") as src:
            shard = json.load(src)
        pids = list(shard.keys())
        html_deleted_with_shards += _delete_html_for_pids(
            pids, data_io.DOCS_ABSTRACTS_DIR)
        f.unlink()
        deleted_shards.append(month_str)
        LOG.info(f"  pruned shard {month_str} ({len(pids)} papers)")

    # Orphan-sweep: any HTML whose pid is not in the (now-pruned) data set.
    active_pids = set()
    for f in data_io.DATA_DIR.glob("papers-*.json"):
        with open(f, "r", encoding="utf-8") as src:
            active_pids.update(json.load(src).keys())

    orphan_html = 0
    if data_io.DOCS_ABSTRACTS_DIR.exists():
        for f in data_io.DOCS_ABSTRACTS_DIR.glob("*.html"):
            if f.stem not in active_pids:
                f.unlink()
                orphan_html += 1

    LOG.info(f"DONE. shards_deleted={deleted_shards} "
             f"html_deleted={html_deleted_with_shards} orphan_html={orphan_html}")
    return {
        "deleted_shards": deleted_shards,
        "html_deleted_with_shards": html_deleted_with_shards,
        "orphan_html": orphan_html,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-days", type=int, default=730,
                        help="prune shards whose end is older than this many "
                             "days (default: 730 = 2 years)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    run(threshold_days=args.threshold_days)


if __name__ == "__main__":
    main()
