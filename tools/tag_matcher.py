"""Match canonical tags from abstract text using pre-built regex matchers.

Loaded from tags/canonical.yaml. Each canonical tag has a list of synonyms;
a paper's abstract is scanned with word-boundary, case-insensitive regex.
A paper can match multiple canonical tags (returned sorted for stable diffs).

Used by:
  - daily_arxiv.py / backfill.py to fill `rec["tags"]` at fetch time
  - tools/retag_corpus.py to (re)tag the existing corpus offline
  - tests + validators
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL = ROOT / "tags" / "canonical.yaml"


def load_canonical_tags(yaml_path=DEFAULT_CANONICAL):
    """Read canonical.yaml. Returns {canonical_name: {group, synonyms, freq?}}."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return data


def build_matchers(canonical):
    """Compile one regex per canonical tag, OR-joining all synonyms with \\b."""
    matchers = {}
    for name, meta in canonical.items():
        synonyms = meta.get("synonyms", []) if isinstance(meta, dict) else []
        if not synonyms:
            continue
        # Sort by length desc so longer phrases match before shorter prefixes
        ordered = sorted({s for s in synonyms if s}, key=len, reverse=True)
        escaped = [re.escape(s) for s in ordered]
        pattern = r"\b(?:" + "|".join(escaped) + r")\b"
        matchers[name] = re.compile(pattern, re.IGNORECASE)
    return matchers


def match_tags(text, matchers):
    """Return sorted list of canonical names whose pattern matches in text."""
    if not text:
        return []
    return sorted(name for name, pat in matchers.items() if pat.search(text))
