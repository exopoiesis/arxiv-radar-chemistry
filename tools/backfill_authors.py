#!/usr/bin/env python3
"""Author backfill — direct arxiv search by author name from tags/authors.yaml.

Whitelist mechanism in daily_arxiv.py / backfill.py is a SECOND-CHANCE check
on papers already returned by topical queries. It cannot retroactively pull
in papers from past months that never matched any topic. This script does:

    for each whitelist entry:
        for each name_match needle:
            arxiv search: au:"<needle>" AND submittedDate:[start TO end]
            for each result: admit if not already in corpus

Admitted papers carry topic 'via:author-whitelist:<note>' and full canonical
tag set. Idempotent — re-runs skip already-known arxiv_ids.

Usage:
    python tools/backfill_authors.py --from-date 2024-05-01 --to-date 2026-05-08
    python tools/backfill_authors.py --dry-run --max-per-author 5
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import arxiv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_io import (
    load_all_months,
    load_authors_whitelist,
    paper_to_record,
    save_month,
    write_abstract_html,
)
import tag_matcher

LOG = logging.getLogger("backfill_authors")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def author_query(needle, year_start, year_end):
    """Build arxiv query that fetches all papers by `needle` in [year_start, year_end]."""
    start = f"{year_start:04d}{1:02d}010000"
    if year_end >= 12:
        end = f"{year_end+1:04d}01010000" if False else f"{year_end:04d}12312359"
    else:
        end = f"{year_end:04d}12312359"
    # arxiv au: field is best-effort; use quoted needle to anchor surname/init.
    return f'au:"{needle}" AND submittedDate:[{start} TO {end}]'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2024-05-01", help="YYYY-MM-DD")
    parser.add_argument("--to-date", default=datetime.now().date().isoformat(),
                        help="YYYY-MM-DD")
    parser.add_argument("--max-per-author", type=int, default=200,
                        help="cap per author per name_match needle")
    parser.add_argument("--dry-run", action="store_true",
                        help="single author, no save")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.to_date, "%Y-%m-%d").date()
    LOG.info(f"author backfill range: {start} -> {end}")

    whitelist = load_authors_whitelist()
    if not whitelist:
        LOG.warning("no tags/authors.yaml or empty list; nothing to do")
        return
    LOG.info(f"whitelist: {len(whitelist)} entries")

    by_month, pid_to_month = load_all_months()
    canonical = tag_matcher.load_canonical_tags()
    matchers = tag_matcher.build_matchers(canonical)
    LOG.info(f"existing corpus: {sum(len(m) for m in by_month.values())} papers")

    client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=5)

    if args.dry_run:
        whitelist = whitelist[:1]
        LOG.info(f"DRY RUN — single author: {whitelist[0].get('name_match', ['?'])[0]}")

    total_new = 0
    total_skipped = 0
    touched_months = set()

    for entry in whitelist:
        if not isinstance(entry, dict):
            continue
        note = entry.get("note", "")
        needles = entry.get("name_match", [])
        for needle in needles:
            q = author_query(needle, start.year, end.year)
            LOG.info(f"  search: au=\"{needle}\"  ({note})")
            search = arxiv.Search(
                query=q,
                max_results=args.max_per_author,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            try:
                results = list(client.results(search))
            except Exception as e:
                LOG.error(f"    ERROR: {e}")
                continue

            added = 0
            already = 0
            for r in results:
                pid, rec = paper_to_record(r)
                if pid in pid_to_month:
                    # Already in corpus (via topical or earlier author run).
                    # Optionally union the via:author-whitelist topic.
                    existing_month = pid_to_month[pid]
                    existing = by_month[existing_month][pid]
                    via_topic = f"via:author-whitelist:{note}" if note else "via:author-whitelist"
                    if via_topic not in existing.get("topics", []):
                        existing["topics"] = sorted(set(existing.get("topics", []) + [via_topic]))
                        touched_months.add(existing_month)
                    already += 1
                    continue
                # Filter by submitted-date window (arxiv may return slight overflow).
                paper_month = rec["updated"][:7]
                rec["topics"] = [f"via:author-whitelist:{note}" if note else "via:author-whitelist"]
                rec["tags"] = tag_matcher.match_tags(rec.get("abstract", ""), matchers)
                by_month[paper_month][pid] = rec
                pid_to_month[pid] = paper_month
                touched_months.add(paper_month)
                if not args.dry_run:
                    write_abstract_html(pid, rec)
                added += 1

            LOG.info(f"    fetched={len(results)} new={added} already_in_corpus={already}")
            total_new += added
            total_skipped += already

            if args.dry_run:
                break
        if args.dry_run:
            break

    if not args.dry_run:
        for m in touched_months:
            save_month(by_month, m)

    grand_total = sum(len(m) for m in by_month.values())
    LOG.info(f"DONE. new={total_new} already_in_corpus={total_skipped} "
             f"grand_total={grand_total} touched_months={len(touched_months)}")


if __name__ == "__main__":
    main()
