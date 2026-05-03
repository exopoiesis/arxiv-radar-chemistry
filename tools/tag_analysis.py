#!/usr/bin/env python3
"""Phase 2: run keyword extraction algorithms over the paper corpus.

Produces per-algorithm candidate lists for human curation. Output goes to
tags/ (or --out-dir) as:
  candidates_<algo>.json  — list of {term, score}, ranked desc
  comparison.md           — terms grouped by how many algorithms found them

Algorithms (both run by default, fast, no model downloads):
  tfidf   — sklearn TfidfVectorizer, multi-word ngrams
  yake    — statistical, position-aware, no training

These two were kept after the chemistry-corpus pilot. RAKE (graph
co-occurrence) was hijacked by URLs and inline arxiv refs even after
cleaning, and KeyBERT (sentence-transformers, ~80 MB model) didn't pay
its compute cost on technical corpora with well-established terminology.

Usage:
    python tools/tag_analysis.py --data-dir data1
    python tools/tag_analysis.py --algorithms tfidf,yake
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_io

LOG = logging.getLogger("tag_analysis")

URL_RE = re.compile(r"https?://\S+|www\.\S+|ftp://\S+", re.IGNORECASE)
ARXIV_ID_RE = re.compile(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b")

# Generic paper-writing and ML-cliche terms that pollute top candidates without
# being topic-bearing. Combined with NLTK/sklearn English stopwords for all
# extractors. Curated from the first run on data1 — biggest noise sources first.
DOMAIN_STOPWORDS = frozenset({
    # paper-writing boilerplate
    "propose", "proposed", "proposes", "proposing",
    "novel", "approach", "approaches",
    "method", "methods", "methodology",
    "framework", "frameworks",
    "paper", "work", "study", "studies",
    "results", "result", "demonstrate", "demonstrates", "demonstrated",
    "show", "shows", "showed", "shown",
    "present", "presents", "presented", "presenting",
    "introduce", "introduces", "introduced",
    "based", "using", "used", "use", "uses",
    "achieve", "achieves", "achieved",
    "existing", "current", "recent", "previous", "prior",
    "compared", "comparison", "compare",
    # vague qualifiers
    "various", "different", "several", "many", "multiple",
    "performance", "effective", "efficient", "robust",
    "high", "higher", "highest", "low", "lower", "lowest",
    "first", "second", "best", "better",
    "state", "art",  # "state of the art"
    # ML clichés that don't convey topic
    "training", "trained", "train",
    "tasks", "task",
    "available", "open", "code",
    # connectives that survived English stoplist
    "via", "thus", "however",
    # phrases (joined by space) — stop_words filters these as combined when
    # tokenizer keeps them; otherwise their constituents are caught above
    "extensive", "experiments",
    "outperforms", "state-of-the-art",
    "across", "diverse",
    "address", "challenges",
    "improve", "improves", "improvement",
    "achieves", "achieving",
    "specifically",
})


def clean_abstract(text):
    """Strip URLs and bare arxiv-id references; collapse whitespace.

    Run on every abstract before tag extraction — ensures GitHub URLs,
    project links, and inline arxiv references don't surface as candidates.
    """
    text = URL_RE.sub(" ", text)
    text = ARXIV_ID_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect_corpus(by_month):
    """Yield cleaned, non-empty abstracts from all loaded papers."""
    docs = []
    for month_data in by_month.values():
        for rec in month_data.values():
            text = rec.get("abstract", "") or ""
            cleaned = clean_abstract(text)
            if cleaned:
                docs.append(cleaned)
    return docs


def _english_stopwords_union_domain():
    """Combine NLTK English stopwords with our domain blocklist, lowercased."""
    try:
        from nltk.corpus import stopwords as nltk_stopwords
        try:
            base = set(nltk_stopwords.words("english"))
        except LookupError:
            import nltk
            nltk.download("stopwords", quiet=True)
            base = set(nltk_stopwords.words("english"))
    except ImportError:
        base = set()
    return base | set(DOMAIN_STOPWORDS)


def extract_tfidf(documents, top_n=200, ngram_range=(2, 3)):
    """Aggregate TF-IDF score across all docs; return top-N (term, score).

    Default ngram_range=(2, 3) — only multi-word terms. Single words rarely
    convey topic on their own (e.g. 'model', 'graph') and dominate the top.
    Pass (1, 3) explicitly if unigrams are wanted.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    stop_words = list(_english_stopwords_union_domain())
    vec = TfidfVectorizer(
        ngram_range=ngram_range,
        stop_words=stop_words,
        max_df=0.9,
        min_df=2,
        lowercase=True,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z+-]*[a-zA-Z]\b",  # alpha tokens, allow + and -
    )
    matrix = vec.fit_transform(documents)
    scores = matrix.sum(axis=0).A1.tolist()
    feature_names = vec.get_feature_names_out()
    pairs = [(str(t), float(s)) for t, s in zip(feature_names, scores)]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:top_n]


def extract_yake(documents, top_n=200):
    """YAKE statistical extraction. Lower native score = better; we invert so
    higher = better for consistency with other algorithms."""
    import yake
    extractor = yake.KeywordExtractor(
        lan="en", n=3, top=top_n, dedupLim=0.7,
        stopwords=_english_stopwords_union_domain(),
    )
    text = "\n\n".join(documents)
    keywords = extractor.extract_keywords(text)
    pairs = [(str(t), 1.0 / (float(s) + 1e-3)) for t, s in keywords]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:top_n]


ALGORITHMS = {
    "tfidf": extract_tfidf,
    "yake": extract_yake,
}


def write_candidates(results, out_dir):
    """Save per-algorithm candidates to <out_dir>/candidates_<algo>.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for algo, pairs in results.items():
        path = out_dir / f"candidates_{algo}.json"
        path.write_text(
            json.dumps([{"term": t, "score": s} for t, s in pairs],
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


def write_comparison(results, out_path):
    """Markdown report grouping terms by how many algorithms surfaced them.

    Term matching is case-insensitive (DFT and dft count as the same term).
    """
    term_to_algos = {}
    for algo, pairs in results.items():
        for term, _ in pairs:
            key = term.lower()
            term_to_algos.setdefault(key, set()).add(algo)

    by_overlap = {}
    for term, algos in term_to_algos.items():
        by_overlap.setdefault(len(algos), []).append((term, sorted(algos)))

    lines = ["# Tag candidate comparison", ""]
    lines.append(f"Algorithms run: {sorted(results.keys())}")
    lines.append("")
    for n in sorted(by_overlap.keys(), reverse=True):
        terms = sorted(by_overlap[n])
        lines.append(f"## Found in {n} algorithm(s) — {len(terms)} terms")
        lines.append("")
        for term, algos in terms[:200]:
            lines.append(f"- `{term}` ({', '.join(algos)})")
        lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None,
                        help="override data_io.DATA_DIR (default: ./data)")
    parser.add_argument("--out-dir", default=None,
                        help="output directory (default: <repo>/tags)")
    parser.add_argument("--algorithms", default="tfidf,yake",
                        help="comma-separated subset of " + ",".join(ALGORITHMS))
    parser.add_argument("--top-n", type=int, default=200)
    parser.add_argument("--max-docs", type=int, default=None,
                        help="cap corpus size (useful for quick iteration)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s %(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    if args.data_dir:
        data_io.DATA_DIR = Path(args.data_dir)
    out_dir = Path(args.out_dir) if args.out_dir else (data_io.ROOT / "tags")

    LOG.info(f"corpus from {data_io.DATA_DIR}")
    by_month, _ = data_io.load_all_months()
    docs = collect_corpus(by_month)
    if args.max_docs:
        docs = docs[: args.max_docs]
    LOG.info(f"loaded {len(docs)} non-empty abstracts")

    algos = [a.strip() for a in args.algorithms.split(",") if a.strip()]
    results = {}
    for algo in algos:
        if algo not in ALGORITHMS:
            LOG.warning(f"unknown algorithm: {algo}; skipping")
            continue
        LOG.info(f"running {algo}...")
        results[algo] = ALGORITHMS[algo](docs, top_n=args.top_n)
        LOG.info(f"  {algo}: {len(results[algo])} candidates")

    write_candidates(results, out_dir)
    write_comparison(results, out_dir / "comparison.md")
    LOG.info(f"DONE. candidates → {out_dir}, comparison → {out_dir/'comparison.md'}")


if __name__ == "__main__":
    main()
