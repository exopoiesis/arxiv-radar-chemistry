# Chemistry arxiv-radar — technical guide

Maintainer / forker reference for `daily-arxiv-Chemistry`. Covers the
architecture, every script in the pipeline, the on-disk data layout, the
dev workflow, and what to change when forking this layer onto a different
domain (physics, polymers, etc.).

The end-user landing is `index.md` (rendered on GitHub Pages); this file
documents how it gets built and maintained.

---

## What this is

A fork of [Vincentqyw/cv-arxiv-daily](https://github.com/Vincentqyw/cv-arxiv-daily)
extended into a small research feed for AI-for-chemistry papers:

- **~14 500 papers** with abstracts, 26 monthly shards (2024-03 → 2026-04)
- **46 canonical tags** in 8 groups, runtime keyword-matched
- **230 pre-rendered tag pages** (46 tags × 5 windows: 7 / 30 / 90 / 360 / all)
- **Compact landing** with right-side tag sidebar and a popup-modal abstract reader
- **Light / dark theme** persisted per-user via `localStorage`
- **Monthly prune** of shards + popup HTML older than 2 years (deletion, not archive — arxiv.org is the canonical copy)

arXiv metadata (incl. abstracts) is **CC0 1.0**, so storing it in a public
repo is fine. PDFs / LaTeX are not stored — only the metadata records.

---

## Architecture in one diagram

```
arXiv API
    │
    ▼
┌──────────────────────┐  inline writes
│ backfill.py /        │──────────────────┐
│ daily_arxiv.py       │                  │
└──────────────────────┘                  ▼
    │            ┌────────────────────────────────────────┐
    ▼            │ data/papers-YYYY-MM.json   (canonical) │
              ┌─►│ docs/abstracts/<id>.html   (popup)     │
              │  └────────────────────────────────────────┘
              │
   ┌──────────┴───────────┬──────────────────┬────────────────────┐
   │                      │                  │                    │
   ▼                      ▼                  ▼                    ▼
render_abstracts.py   render_readme.py   render_tag_pages.py   render_index.py
                          │
                          │  writes md for selected, prunes orphans
                          ▼
        abstracts/<year>/<id>.md  (~316 files, README-linked only)
```

After everything runs you also get:

- `docs/_data/tag_index.yml` — sidebar source (sorted by 30-day count desc)
- `docs/tag/<tag>-<window>.md` × 230 — pre-rendered listings
- `docs/index.md` — Pages landing
- `README.md` (repo root) — top-50 per topic, table-of-contents

---

## Daily pipeline (what `daily_arxiv.py` does)

Idempotent — safe to re-run any number of times per day. GitHub Actions
fires it on a 12-hour cron (`.github/workflows/Chemistry-arxiv-daily.yml`).

| # | Step | Script | Output |
|---|------|--------|--------|
| 1 | Fetch current month's papers per topic | `daily_arxiv.fetch_current_month` | appended to `data/papers-YYYY-MM.json` |
| 2 | Inline write popup fragment | `data_io.write_abstract_html` | `docs/abstracts/<id>.html` |
| 3 | Backfill HTML for any missing | `tools/render_abstracts.py` | as above |
| 4 | Render README + sync legacy md | `tools/render_readme.py` | `README.md`; `abstracts/<year>/*.md` |
| 5 | Pre-render tag pages | `tools/render_tag_pages.py` | `docs/tag/*.md` × 230 |
| 6 | Render Pages landing + sidebar data | `tools/render_index.py` | `docs/index.md`, `docs/_data/tag_index.yml` |

A separate workflow prunes anything older than 2 years:

| Workflow | Cron | Script | Action |
|----------|------|--------|--------|
| `monthly-archive.yml` | `0 2 1 * *` | `tools/archive_old.py` | Deletes `data/papers-YYYY-MM.json` whose month-end is past cutoff; deletes corresponding `docs/abstracts/<id>.html`; orphan-sweeps any popup HTML whose pid is no longer in `data/`. No gzip, no archive directory. |

---

## Scripts catalog

### Pipeline

| File | Purpose |
|------|---------|
| `daily_arxiv.py` | Daily orchestrator (steps 1–6 above). |
| `tools/backfill.py` | Historical fetch with date-sharding (per topic × month) and a checkpoint at `data/backfill_checkpoint.json`. Idempotent; resumable. |
| `tools/render_abstracts.py` | Default: writes `docs/abstracts/<id>.html` for every paper in `data/`. `--include-md` also writes the legacy markdown variants. `--force` rewrites existing files. |
| `tools/render_readme.py` | Builds the repo-root `README.md` (top-N per topic). After writing it, scans the markdown for `abstracts/<year>/<id>.md` references, ensures those files exist (calls `write_abstract`), and deletes any markdown not currently linked. Keeps `/abstracts/` bounded. |
| `tools/render_tag_pages.py` | For every canonical tag × 5 windows, generates an HTML-table listing of matching papers, sorted by `updated` desc. Each title becomes an `<a class="abstract-popup">` so the JS modal can intercept clicks. Per-paper tag links are window-aware: viewing 7d shows 7d links to other tags. |
| `tools/render_index.py` | Builds `docs/index.md` (corpus stats + top-30 recent) and writes `docs/_data/tag_index.yml` (sidebar source). Sorts the sidebar by 30-day count descending. |
| `tools/archive_old.py` | Pure deletion (no archive). Deletes shards whose month-end falls before today − threshold (default 730 days), removes the corresponding `docs/abstracts/<id>.html` for each paper inside, then orphan-sweeps any popup HTML whose pid is no longer present in any shard. arxiv.org is the canonical metadata copy; we don't replicate locally. |

### Helpers

| File | Purpose |
|------|---------|
| `tools/data_io.py` | Shared library: schema, I/O, query parsing, chemistry filter, URL linkifier, abstract renderers (markdown + HTML fragment), legacy + new path helpers, `iter_papers_in_window`. |
| `tools/tag_matcher.py` | Loads `tags/canonical.yaml` + `tags/synonyms.yaml`, builds word-bounded regexes, returns sorted matched tags for a given abstract. Pure runtime — no ML model in prod. |
| `tools/tag_analysis.py` | Offline: runs TF-IDF + YAKE candidate extraction on the corpus to inform manual curation of `canonical.yaml`. Both run by default, both fast, no model downloads. RAKE and KeyBERT were tried in the chemistry pilot and dropped (RAKE was hijacked by URLs even after cleaning; KeyBERT didn't earn its compute on technical terminology). |
| `tools/retag_corpus.py` | One-shot: re-tags every paper in `data/` after edits to `canonical.yaml` / `synonyms.yaml`. |
| `tools/filter_corpus.py` | One-shot: re-applies the chemistry filter to existing shards, used after tightening `CHEM_PATTERN`. |
| `tools/split_by_month.py` | One-shot migration: monolithic JSON → monthly shards. Historical, kept for reference. |
| `tools/prune_old_abstract_md.py` | Standalone version of the prune logic now baked into `render_readme.py`. Dry-run friendly (`--dry-run`). |

### Config

| File | Purpose |
|------|---------|
| `config.yaml` | 7 topics × filters. Three forms: bare phrase, multi-word (auto-quoted), `RAW:` (verbatim — used to AND a greedy term with chemistry context). |
| `tags/canonical.yaml` | 46 canonical tags grouped by category (methods / architectures / llm× / tasks / bio / domain / properties / specialized). |
| `tags/synonyms.yaml` | Maps surface-form keywords to canonical tags. Word-bounded matching at runtime. |
| `docs/_config.yml` | Jekyll config: site title, description, remote_theme (`jekyll/minima`), `header_pages: []` (we override the header anyway). |

---

## Data layout

```
data/
├── papers-2024-04.json … papers-2026-04.json   ← 25 monthly shards
└── backfill_checkpoint.json                    ← 182/182 (topic × month) done

abstracts/                                      ← legacy markdown, README-linked only
├── 2024/<id>.md
├── 2025/<id>.md
└── 2026/<id>.md                                ← total ~316 files

docs/
├── _config.yml
├── _data/tag_index.yml                         ← sidebar source
├── _includes/                                  ← head, header, tag_sidebar
├── _layouts/page.html                          ← grid: main + sidebar
├── assets/css/site.css                         ← themed, single source
├── assets/js/site.js                           ← theme toggle + popup
├── abstracts/<id>.html                         ← popup fragment, ~14 500 files
├── tag/<tag>-<window>.md                       ← 46 × 5 = 230 files
└── index.md
```

### Schema (per paper, in `data/papers-YYYY-MM.json`)

Flat dict keyed by `arxiv_id` (version stripped):

```json
{
  "2510.05482": {
    "title": "...",
    "first_author": "Smith",
    "authors": ["Smith", "Doe"],
    "abstract": "...",
    "primary_category": "cs.LG",
    "categories": ["cs.LG", "physics.chem-ph"],
    "published": "2025-10-07",
    "updated": "2026-04-23",
    "comment": null,
    "pdf_url": "http://arxiv.org/pdf/2510.05482",
    "topics": ["Quantum Chemistry & Force Fields"],
    "tags": ["molecular-dynamics", "drug-discovery"]
  }
}
```

`topics` come from `config.yaml` topic names (a paper can match several).
`tags` come from `tags/canonical.yaml`, matched at fetch time by
`tag_matcher.match_tags(abstract)`.

### Sharding rule

A paper goes into the shard `papers-<updated[:7]>.json`. **Once placed,
it stays** — if a v3 lands a month later, the daily fetcher sees the ID is
already known and only merges new topics into the existing record; it does
not move the paper between shards.

---

## Pages site

### Layout structure

```
_layouts/
├── (default ← from remote_theme jekyll/minima)
└── page.html      ← extends default, adds the .layout-grid wrapper
                     (main + tag sidebar) used by index + tag pages

_includes/
├── head.html      ← overrides minima default; adds theme-init script,
                     site.css, site.js
├── header.html    ← overrides minima; site title + theme toggle (no
                     auto-listing of all 230 tag pages as nav links)
└── tag_sidebar.html
                   ← reads site.data.tag_index, renders the right column
```

### Theme system

Two themes via CSS variables on `:root` and `[data-theme="dark"]`. The
toggle button in the site header swaps the attribute and saves
`localStorage.theme = "dark" | "light"`. A small inline script in
`_includes/head.html` reads the value and applies it **before** stylesheets
paint, so there's no flash of unstyled / light-flash on dark refresh.

### Abstract popup

Each paper title in tag pages is wrapped:

```html
<a class="abstract-popup paper-title-link" href="../abstracts/<id>.html">title</a>
```

`docs/assets/js/site.js` listens for clicks via event delegation, calls
`fetch(href)`, and injects the response into a fixed-position overlay.
`Esc` and click-outside close. Modifier-clicks (Ctrl / ⌘ / shift /
middle) fall through, so users can still open the standalone fragment in
a new tab. The fragment is cached in memory so re-opening the same paper
is free.

The fragment files are full HTML `<article>` blocks generated by
`data_io.render_abstract_html_fragment`. All user-controlled fields
(title, authors, abstract) are HTML-escaped; URLs in the abstract body
are linkified after escaping to prevent injection.

---

## Local preview

Ruby is not required locally — Jekyll runs in Docker:

```bash
bash tmp/jekyll_serve_arxiv.sh
# → http://localhost:4000
# stop:    docker rm -f arxiv-jekyll
# logs:    docker logs -f arxiv-jekyll
```

Notes:

- First build ~30 sec (jekyll/jekyll:4.2.2 image, gems in a named
  Docker volume, remote theme `jekyll/minima` fetched at build).
- Watch / auto-regenerate is on but unreliable on Windows + Docker
  (file events don't always cross the bind-mount). For changes to
  `_config.yml`, `_layouts/`, `_includes/`, `_data/`,
  `assets/css/`, `assets/js/`, prefer
  `docker restart arxiv-jekyll`.
- Regenerated content under `docs/abstracts/`, `docs/tag/`,
  `docs/index.md` is picked up by watch within a few seconds in
  practice.

---

## Tests

```bash
.venv/Scripts/pytest.exe tests/ -q
# 128 tests; ~3 s
```

Coverage map:

| Test file | Covers |
|-----------|--------|
| `test_data_io.py` | save/load, `paper_to_record`, chemistry filter, linkify, render_abstract_md, **render_abstract_html_fragment** (escaping, structure), `write_abstract_html` |
| `test_backfill.py` | API mocked: chemistry filter, topic merge, checkpoint, sharding |
| `test_render_abstracts.py` | default (HTML-only), `--include-md`, idempotency, `--force` |
| `test_render_readme.py` | TOC, top-N truncation, anchors |
| `test_split_by_month.py` | merge logic across month boundary |
| `test_tag_analysis.py` | YAKE / TF-IDF candidate extraction |
| `test_filter_corpus.py` | batch chemistry re-filter |
| `test_tag_matcher.py` | canonical / synonym loading, word-boundary regex |
| `test_retag_corpus.py` | tag reassignment in-place |
| `test_render_tag_pages.py` | tag/window filtering, sort, **popup link wrapping**, **window-aware per-paper tags**, **self-link skip** |
| `test_render_index.py` | sidebar data emission, freq counts |
| `test_archive_old.py` | month-end cutoff math, popup-HTML deletion alongside shard, orphan-HTML sweep, idempotency |

---

## Forking onto a different domain

The pipeline is mostly domain-neutral except where it isn't. To fork
this onto, say, `daily-arxiv-physics`:

1. **`tools/data_io.py` → `CHEM_PATTERN`** — hard-coded regex of
   chemistry-context terms. Replace with the new domain's vocabulary,
   or refactor to load from `config.yaml`. This is the single biggest
   non-config change.
2. **`config.yaml`** — replace the 7 chemistry topics + their `RAW:`
   AND-context filters with domain-specific ones.
3. **`tags/canonical.yaml`** + **`tags/synonyms.yaml`** — re-curate.
   Run `tools/tag_analysis.py` after the first backfill to surface
   high-frequency candidate terms.
4. **`docs/_config.yml`** — `title`, `description`, `github.zip_url`.
5. **Repo / Pages metadata** — repo name, description, badges in
   `README.md` template if any.
6. Empty `data/`, `abstracts/`, `docs/abstracts/`,
   `docs/tag/`, `docs/_data/`. Run `tools/backfill.py` and let the
   daily pipeline shape the rest.

GitHub Pages serves from `/docs/` (configured in repo settings); no
build action needed beyond pushing.

---

## Attribution

Forked and extended from
[Vincentqyw/cv-arxiv-daily](https://github.com/Vincentqyw/cv-arxiv-daily)
(MIT). arXiv metadata is CC0 1.0
(<https://info.arxiv.org/help/api/tou.html>).
