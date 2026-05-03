#!/usr/bin/env python3
"""Re-tag the existing corpus from canonical.yaml + re-render abstract files.

For each paper in data/papers-*.json:
  1. Compute current canonical tags via tag_matcher.match_tags
  2. If different from rec['tags'], update + regenerate abstract markdown
  3. Otherwise leave untouched (idempotent)

Use this after canonical.yaml changes (new tag, edited synonyms) or after
data_io.render_abstract_md changes (new frontmatter, linkify, etc) to roll
the changes through the entire corpus offline.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io
import tag_matcher

LOG = logging.getLogger("retag_corpus")


def run(canonical_path=None):
    canonical = tag_matcher.load_canonical_tags(
        canonical_path or tag_matcher.DEFAULT_CANONICAL)
    matchers = tag_matcher.build_matchers(canonical)
    LOG.info(f"loaded {len(canonical)} canonical tags, {len(matchers)} matchers")

    by_month, _ = data_io.load_all_months()
    total = sum(len(m) for m in by_month.values())
    LOG.info(f"corpus: {total} papers across {len(by_month)} months")

    changed_total = unchanged_total = 0
    touched_months = set()

    for month, papers in by_month.items():
        for pid, rec in papers.items():
            new_tags = tag_matcher.match_tags(rec.get("abstract", ""), matchers)
            if new_tags == sorted(rec.get("tags", [])):
                unchanged_total += 1
                continue
            rec["tags"] = new_tags
            data_io.write_abstract(pid, rec, force=True)
            touched_months.add(month)
            changed_total += 1

    for m in touched_months:
        data_io.save_month(by_month, m)

    LOG.info(f"DONE. changed={changed_total} unchanged={unchanged_total} "
             f"total={changed_total + unchanged_total} "
             f"touched_months={len(touched_months)}")
    return {"changed": changed_total, "unchanged": unchanged_total,
            "total": changed_total + unchanged_total}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", default=None,
                        help="path to canonical.yaml (default: tags/canonical.yaml)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    run(args.canonical)


if __name__ == "__main__":
    main()
