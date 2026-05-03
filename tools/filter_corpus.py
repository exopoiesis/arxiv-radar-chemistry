#!/usr/bin/env python3
"""Apply chemistry-context filter to existing corpus locally.

Phase 2 helper: instead of re-fetching from arXiv (which we can also do, but
slower and risks more rate-limit hits), use the data we already have. Each
paper's abstract is scanned for chemistry-relevant keywords; non-matching
papers are dropped. Output is written to a separate folder so the original
corpus is untouched.

Usage:
    python tools/filter_corpus.py                     # default: data → data_filtered/
    python tools/filter_corpus.py --out-dir my_dir
"""
import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io
from data_io import is_chemistry_paper  # noqa: F401  (re-export for tests/CLI)

LOG = logging.getLogger("filter_corpus")


def run(out_dir):
    """Filter all months under data_io.DATA_DIR, write to out_dir, return stats."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_month, _ = data_io.load_all_months()
    kept_total = dropped_total = 0
    dropped_by_topic = Counter()
    kept_by_topic = Counter()

    for month, papers in sorted(by_month.items()):
        kept = {}
        for pid, rec in papers.items():
            if is_chemistry_paper(rec.get("abstract", "")):
                kept[pid] = rec
                for t in rec.get("topics", []):
                    kept_by_topic[t] += 1
            else:
                for t in rec.get("topics", []):
                    dropped_by_topic[t] += 1
        kept_total += len(kept)
        dropped_total += len(papers) - len(kept)

        out_path = out_dir / f"papers-{month}.json"
        tmp = out_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=1, sort_keys=True)
        tmp.replace(out_path)
        LOG.info(f"  {month}: kept={len(kept):>5}, dropped={len(papers)-len(kept):>5}")

    return {
        "kept": kept_total,
        "dropped": dropped_total,
        "kept_by_topic": dict(kept_by_topic),
        "dropped_by_topic": dict(dropped_by_topic),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None,
                        help="override data_io.DATA_DIR (default: ./data)")
    parser.add_argument("--out-dir", default=None,
                        help="output folder (default: <repo>/data_filtered)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    if args.data_dir:
        data_io.DATA_DIR = Path(args.data_dir)
    out_dir = Path(args.out_dir) if args.out_dir else (data_io.ROOT / "data_filtered")

    LOG.info(f"input: {data_io.DATA_DIR}")
    LOG.info(f"output: {out_dir}")
    stats = run(out_dir)
    LOG.info(f"DONE. kept={stats['kept']} dropped={stats['dropped']}")
    LOG.info("dropped per topic:")
    for t, n in sorted(stats["dropped_by_topic"].items(), key=lambda x: -x[1]):
        LOG.info(f"  {n:>6}  {t}")
    LOG.info("kept per topic:")
    for t, n in sorted(stats["kept_by_topic"].items(), key=lambda x: -x[1]):
        LOG.info(f"  {n:>6}  {t}")


if __name__ == "__main__":
    main()
