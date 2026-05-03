#!/usr/bin/env python3
"""Backfill arXiv papers with abstracts into monthly files data/papers-YYYY-MM.json.

Sharded by (topic, year-month) on the fetch side to stay under the per-query
30k cap. Storage is sharded by `updated` month — paper goes to whatever month
its latest revision belongs to. A checkpoint file records completed (topic,
fetch-month) pairs so re-runs skip them.

Reusable across domain repos: reads keyword filters from config.yaml. To use
in another repo, copy this file + split_by_month.py + .gitignore + venv setup.

Usage:
    python tools/backfill.py --from-date 2024-07-01 --to-date 2026-04-26
    python tools/backfill.py --dry-run                        # one shard, no save
    python tools/backfill.py --topics "Quantum Chemistry & Force Fields"
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import arxiv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_io import (
    is_chemistry_paper,
    load_all_months,
    load_keyword_queries as _load_keyword_queries,
    paper_to_record,
    save_month,
    write_abstract_html,
)
import tag_matcher

LOG = logging.getLogger("backfill")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHECKPOINT_FILE = DATA_DIR / "backfill_checkpoint.json"
CONFIG_FILE = ROOT / "config.yaml"


def load_keyword_queries():
    """Thin wrapper over data_io.load_keyword_queries with backfill's CONFIG_FILE."""
    return _load_keyword_queries(CONFIG_FILE)


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_checkpoint(done):
    DATA_DIR.mkdir(exist_ok=True)
    tmp = CHECKPOINT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f, indent=1)
    tmp.replace(CHECKPOINT_FILE)


def month_shards(start_date, end_date):
    cur = datetime(start_date.year, start_date.month, 1)
    end = datetime(end_date.year, end_date.month, 1)
    while cur <= end:
        yield cur.year, cur.month
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)


def shard_query(keyword_query, year, month):
    start = f"{year:04d}{month:02d}010000"
    if month == 12:
        next_y, next_m = year + 1, 1
    else:
        next_y, next_m = year, month + 1
    end = f"{next_y:04d}{next_m:02d}010000"
    return f"({keyword_query}) AND submittedDate:[{start} TO {end}]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2024-07-01", help="YYYY-MM-DD")
    parser.add_argument("--to-date", default=datetime.now().date().isoformat(),
                        help="YYYY-MM-DD (inclusive month)")
    parser.add_argument("--topics", help="comma-separated topics; default: all from config.yaml")
    parser.add_argument("--max-per-shard", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true",
                        help="single shard, no save, prints schema sample")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.to_date, "%Y-%m-%d").date()
    LOG.info(f"Range: {start} -> {end}")

    queries = load_keyword_queries()
    if args.topics:
        wanted = {t.strip() for t in args.topics.split(",")}
        queries = {k: v for k, v in queries.items() if k in wanted}
        if not queries:
            LOG.error(f"No matching topics. Available: {list(load_keyword_queries().keys())}")
            sys.exit(1)
    LOG.info(f"Topics: {list(queries.keys())}")

    by_month, pid_to_month = load_all_months()
    total_existing = sum(len(m) for m in by_month.values())
    done = load_checkpoint()
    canonical = tag_matcher.load_canonical_tags()
    matchers = tag_matcher.build_matchers(canonical)
    LOG.info(f"Loaded {total_existing} existing papers across {len(by_month)} months; "
             f"checkpoints: {len(done)}; canonical tags: {len(canonical)}")

    client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=5)

    shards = [(t, y, m) for t in queries for y, m in month_shards(start, end)]
    if args.dry_run:
        shards = shards[:1]
        LOG.info(f"DRY RUN — shard: {shards[0]}")

    total_new = 0
    total_topic_merges = 0
    for idx, (topic, year, month) in enumerate(shards, 1):
        key = f"{topic}|{year:04d}-{month:02d}"
        if key in done and not args.dry_run:
            continue
        query = shard_query(queries[topic], year, month)
        LOG.info(f"[{idx}/{len(shards)}] {topic} {year}-{month:02d}")
        search = arxiv.Search(
            query=query,
            max_results=args.max_per_shard,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        try:
            results = list(client.results(search))
        except Exception as e:
            LOG.error(f"  ERROR fetching: {e}; will retry on next run")
            continue

        added = 0
        topic_merges = 0
        chem_skipped = 0
        touched = set()
        for r in results:
            pid, rec = paper_to_record(r)
            paper_month = rec["updated"][:7]
            if pid in pid_to_month:
                existing_month = pid_to_month[pid]
                existing = by_month[existing_month][pid]
                if topic not in existing.get("topics", []):
                    existing["topics"] = sorted(set(existing.get("topics", []) + [topic]))
                    topic_merges += 1
                    touched.add(existing_month)
                continue
            if not is_chemistry_paper(rec.get("abstract", "")):
                chem_skipped += 1
                continue
            rec["topics"] = [topic]
            rec["tags"] = tag_matcher.match_tags(rec.get("abstract", ""), matchers)
            by_month[paper_month][pid] = rec
            pid_to_month[pid] = paper_month
            touched.add(paper_month)
            # docs/abstracts/<id>.html for popup (always). The legacy markdown
            # under /abstracts/<year>/ is managed by render_readme.py and only
            # exists for papers it links from README — no inline md write here.
            write_abstract_html(pid, rec)
            added += 1
        total_new += added
        total_topic_merges += topic_merges
        LOG.info(f"  fetched={len(results)} new={added} topic_merges={topic_merges} "
                 f"chem_skipped={chem_skipped} total={sum(len(m) for m in by_month.values())}")

        if args.dry_run:
            if results:
                sample_id, sample_rec = paper_to_record(results[0])
                LOG.info(f"  SAMPLE id={sample_id}")
                LOG.info(f"    title: {sample_rec['title'][:80]}")
                LOG.info(f"    abstract[:200]: {sample_rec['abstract'][:200]}")
                LOG.info(f"    primary_cat: {sample_rec['primary_category']}")
                LOG.info(f"    categories: {sample_rec['categories']}")
                LOG.info(f"    published: {sample_rec['published']} updated: {sample_rec['updated']}")
            break

        # persist all touched months atomically before advancing checkpoint
        for m in touched:
            save_month(by_month, m)
        done.add(key)
        save_checkpoint(done)

    grand_total = sum(len(m) for m in by_month.values())
    LOG.info(f"DONE. new={total_new} topic_merges={total_topic_merges} grand_total={grand_total}")


if __name__ == "__main__":
    main()
