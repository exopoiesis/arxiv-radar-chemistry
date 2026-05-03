#!/usr/bin/env python3
"""Delete abstracts/<year>/<id>.md files that aren't linked from README.

Rationale: HTML fragments at docs/abstracts/<id>.html now serve the popup on
tag/index pages and arxiv-radar-mcp will read papers.json directly. The
markdown abstracts only matter as targets of the README's per-topic top-N
table. After paper rotation, most of the ~14k md files become orphans.

Idempotent: run as often as you like. --dry-run to preview.

NOTE: currently a one-shot. To keep the dir bounded going forward, either run
this from the daily pipeline after render_readme, or have render_readme do
the prune itself.
"""
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_io import ROOT, ABSTRACTS_DIR

LOG = logging.getLogger("prune_old_abstract_md")

README_LINK_RE = re.compile(r"abstracts/(\d{4}\.\d{4,6})\.md")


def collect_referenced(readme_path):
    """Return set of pids referenced as abstracts/<pid>.md in README markdown."""
    text = Path(readme_path).read_text(encoding="utf-8")
    return set(README_LINK_RE.findall(text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default=str(ROOT / "README.md"),
                        help="path to README to scan (default: ./README.md)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be deleted, don't unlink")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    keep = collect_referenced(args.readme)
    LOG.info(f"README references {len(keep)} unique abstract md files")

    if not ABSTRACTS_DIR.exists():
        LOG.warning(f"{ABSTRACTS_DIR} does not exist; nothing to do")
        return

    deleted = kept = 0
    for f in ABSTRACTS_DIR.rglob("*.md"):
        if f.stem in keep:
            kept += 1
            continue
        if args.dry_run:
            deleted += 1
        else:
            f.unlink()
            deleted += 1

    # Sweep empty year-dirs.
    if not args.dry_run:
        for d in sorted(ABSTRACTS_DIR.iterdir()):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    verb = "would delete" if args.dry_run else "deleted"
    LOG.info(f"DONE. {verb}={deleted} kept={kept}")


if __name__ == "__main__":
    main()
