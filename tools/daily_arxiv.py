#!/usr/bin/env python3
"""Daily orchestrator for arxiv-radar.

Steps (all idempotent — safe to re-run any number of times per day):
  1. Fetch current month's papers from arXiv for every topic in config.yaml
  2. Append new papers to data/papers-YYYY-MM.json (skip already-known IDs)
     and write docs/abstracts/<id>.html (popup fragment) inline.
  3. render_abstracts.py — backfills HTML for any paper missing one.
  4. render_readme.py — README + sync of legacy /abstracts/<year>/<id>.md
     (writes the ones it links, prunes the rest).
  5. render_tag_pages.py — 230 pre-generated tag/window pages.
  6. render_index.py — Pages landing + _data/tag_index.yml for sidebar.

GitHub Actions workflow calls `python tools/daily_arxiv.py` on a daily cron.
"""
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

import arxiv

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from data_io import (
    is_chemistry_paper,
    is_whitelisted_author,
    load_authors_whitelist,
    load_all_months,
    load_keyword_queries as _load_keyword_queries,
    paper_to_record,
    save_month,
    write_abstract_html,
)
import tag_matcher

LOG = logging.getLogger("daily")
CONFIG_FILE = ROOT / "config.yaml"


def load_keyword_queries():
    return _load_keyword_queries(CONFIG_FILE)


def shard_query_current_month(keyword_query, year, month):
    start = f"{year:04d}{month:02d}010000"
    if month == 12:
        next_y, next_m = year + 1, 1
    else:
        next_y, next_m = year, month + 1
    end = f"{next_y:04d}{next_m:02d}010000"
    return f"({keyword_query}) AND submittedDate:[{start} TO {end}]"


def fetch_current_month(client, queries):
    """Iterate topics, fetch current-month shard for each. Returns merged-state by_month dict."""
    today = date.today()
    by_month, pid_to_month = load_all_months()
    canonical = tag_matcher.load_canonical_tags()
    matchers = tag_matcher.build_matchers(canonical)
    LOG.info(f"loaded {sum(len(m) for m in by_month.values())} existing papers; "
             f"canonical tags: {len(canonical)}")
    whitelist = load_authors_whitelist()
    if whitelist:
        LOG.info(f"author whitelist: {len(whitelist)} entries")

    new_total = 0
    touched = set()
    for topic, query in queries.items():
        full_q = shard_query_current_month(query, today.year, today.month)
        search = arxiv.Search(
            query=full_q,
            max_results=2000,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        try:
            results = list(client.results(search))
        except Exception as e:
            LOG.error(f"  ERROR for {topic}: {e}")
            continue
        added = 0
        topic_merges = 0
        chem_skipped = 0
        whitelist_admitted = 0
        for r in results:
            pid, rec = paper_to_record(r)
            paper_month = rec["updated"][:7]
            if pid in pid_to_month:
                existing = by_month[pid_to_month[pid]][pid]
                if topic not in existing.get("topics", []):
                    existing["topics"] = sorted(set(existing.get("topics", []) + [topic]))
                    topic_merges += 1
                    touched.add(pid_to_month[pid])
                continue
            relevant = is_chemistry_paper(rec.get("abstract", ""))
            wl_note = None
            if not relevant:
                wl_note = is_whitelisted_author(rec.get("authors", []), whitelist)
                if wl_note is None:
                    chem_skipped += 1
                    continue
            rec["topics"] = [topic]
            if wl_note:
                rec["topics"].append(f"via:author-whitelist:{wl_note}")
                whitelist_admitted += 1
            rec["tags"] = tag_matcher.match_tags(rec.get("abstract", ""), matchers)
            by_month[paper_month][pid] = rec
            pid_to_month[pid] = paper_month
            touched.add(paper_month)
            write_abstract_html(pid, rec)
            added += 1
        LOG.info(f"  {topic}: fetched={len(results)} new={added} (whitelist={whitelist_admitted}) merged={topic_merges} chem_skipped={chem_skipped}")
        new_total += added

    for m in touched:
        save_month(by_month, m)
    LOG.info(f"fetch done. new={new_total} touched_months={sorted(touched)}")
    return new_total


def main():
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    today = date.today()
    LOG.info(f"daily run for {today.isoformat()}")

    queries = load_keyword_queries()
    LOG.info(f"topics: {list(queries.keys())}")

    client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=5)
    fetch_current_month(client, queries)

    LOG.info("rendering abstracts...")
    subprocess.check_call([sys.executable, str(TOOLS / "render_abstracts.py")])

    LOG.info("rendering README...")
    subprocess.check_call([sys.executable, str(TOOLS / "render_readme.py")])

    LOG.info("rendering tag pages...")
    subprocess.check_call([sys.executable, str(TOOLS / "render_tag_pages.py")])

    LOG.info("rendering Pages index...")
    subprocess.check_call([sys.executable, str(TOOLS / "render_index.py")])

    LOG.info("daily run complete")


if __name__ == "__main__":
    main()
