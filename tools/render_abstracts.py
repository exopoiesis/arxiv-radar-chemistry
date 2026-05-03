#!/usr/bin/env python3
"""Generate per-paper abstract files for every paper in data/papers-*.json.

By default writes ONLY the HTML fragment at docs/abstracts/<id>.html — that's
the popup-served version, needed for every paper. The legacy markdown
abstracts (abstracts/<year>/<id>.md) are managed by render_readme.py: it
emits .md only for the papers it links from README (top-N per topic) and
prunes the rest, keeping the dir bounded at ~300 files.

Idempotent — skips files that exist unless --force is passed.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_io import load_all_months, write_abstract, write_abstract_html

LOG = logging.getLogger("render_abstracts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="rewrite even if abstract files already exist")
    parser.add_argument("--include-md", action="store_true",
                        help="ALSO write the legacy markdown variants for every "
                             "paper. Off by default — render_readme manages md.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    by_month, _ = load_all_months()
    total = sum(len(m) for m in by_month.values())
    LOG.info(f"loaded {total} papers across {len(by_month)} months")

    md_written = md_skipped = html_written = html_skipped = 0
    for month_data in by_month.values():
        for pid, rec in month_data.items():
            if write_abstract_html(pid, rec, force=args.force):
                html_written += 1
            else:
                html_skipped += 1
            if args.include_md:
                if write_abstract(pid, rec, force=args.force):
                    md_written += 1
                else:
                    md_skipped += 1
            if (md_written + html_written) and (md_written + html_written) % 5000 == 0:
                LOG.info(f"  ...md={md_written} html={html_written}")

    LOG.info(f"DONE. html(written={html_written} skipped={html_skipped})  "
             f"md(written={md_written} skipped={md_skipped})")


if __name__ == "__main__":
    main()
