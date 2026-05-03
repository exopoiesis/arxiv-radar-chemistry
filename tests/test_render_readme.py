"""Tests for tools/render_readme.py."""
import re
import sys
from pathlib import Path

import pytest


def _run_render_readme(out_path, top_n=50):
    """Invoke render_readme.main() with patched sys.argv."""
    import render_readme
    saved_argv = sys.argv
    sys.argv = ["render_readme.py", "--top-n", str(top_n), "--out", str(out_path)]
    try:
        render_readme.main()
    finally:
        sys.argv = saved_argv


def test_render_readme_basic(populated_data_dir, tmp_path):
    """Generated README contains both topics from sample data and the date header."""
    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")
    assert "## Updated on" in content
    assert "Topic A" in content
    assert "Topic B" in content
    # 2 papers in Topic A, 1 in Topic B
    assert "(2)" in content
    assert "(1)" in content


def test_render_readme_top_n_limits(populated_data_dir, tmp_path, sample_record):
    """When top-N=1 and topic has 2 papers, only the most recent is shown."""
    import data_io
    # Add a 3rd paper to Topic A to force top-N to truncate.
    by_month, _ = data_io.load_all_months()
    extra = dict(sample_record)
    extra["topics"] = ["Topic A"]
    extra["updated"] = "2025-04-25"  # most recent
    extra["published"] = "2025-04-25"
    by_month["2025-04"]["2504.99999"] = extra
    data_io.save_month(by_month, "2025-04")

    out = tmp_path / "README.md"
    _run_render_readme(out, top_n=1)
    content = out.read_text(encoding="utf-8")
    # Most recent Topic A paper is 2504.99999 (updated 2025-04-25). Older ones excluded.
    assert "2504.99999" in content
    assert "2504.00001" not in content  # older Topic A paper truncated
    assert "2503.00001" not in content  # oldest Topic A paper truncated


def test_render_readme_sort_by_updated_desc(populated_data_dir, tmp_path):
    """Within a topic, more recent papers appear before older ones."""
    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")
    # In Topic A: 2504.00001 (2025-04-15) should appear BEFORE 2503.00001 (2025-03-01)
    pos_recent = content.index("2504.00001")
    pos_old = content.index("2503.00001")
    assert pos_recent < pos_old


def test_render_readme_skips_untagged(populated_data_dir, tmp_path):
    """Papers with empty topics list are not rendered in any section."""
    import data_io
    by_month, _ = data_io.load_all_months()
    untagged = {
        "title": "Untagged paper",
        "first_author": "Z",
        "authors": ["Z"],
        "abstract": "abs",
        "primary_category": "cs.LG",
        "categories": ["cs.LG"],
        "published": "2025-04-26",
        "updated": "2025-04-26",
        "comment": None,
        "pdf_url": "http://arxiv.org/pdf/2504.99998",
        "topics": [],  # untagged
        "tags": [],
    }
    by_month["2025-04"]["2504.99998"] = untagged
    data_io.save_month(by_month, "2025-04")

    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")
    assert "2504.99998" not in content
    assert "Untagged paper" not in content


@pytest.mark.parametrize("header,expected_anchor", [
    # Plain topic
    ("Topic A", "topic-a"),
    # GitHub strips `&` but keeps the spaces around it → double dash
    ("Quantum Chemistry & Force Fields", "quantum-chemistry--force-fields"),
    ("Property Prediction & ADMET", "property-prediction--admet"),
    # Comma also stripped, leaving its surrounding space → produces a dash
    # ("Reaction, Synthesis & Catalysis" → "reaction-synthesis--catalysis":
    #  comma removed leaves single space; ampersand removed leaves double space)
    ("Reaction, Synthesis & Catalysis", "reaction-synthesis--catalysis"),
    # Date in header — periods are stripped
    ("Updated on 2026.04.26", "updated-on-20260426"),
])
def test_topic_anchor_matches_github(header, expected_anchor):
    """Anchor generation matches GitHub's header-to-fragment slug rules."""
    from render_readme import topic_anchor
    assert topic_anchor(header) == expected_anchor


def test_render_readme_toc_anchors_match_section_headers(populated_data_dir, tmp_path):
    """Every TOC link target corresponds to a real ## section's anchor."""
    import data_io
    # Add topics with characters that exercise slug rules.
    by_month, _ = data_io.load_all_months()
    by_month["2025-04"]["2504.00001"]["topics"] = ["Quantum Chemistry & Force Fields"]
    by_month["2025-04"]["2504.00002"]["topics"] = ["Reaction, Synthesis & Catalysis"]
    data_io.save_month(by_month, "2025-04")

    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")

    from render_readme import topic_anchor
    toc_anchors = re.findall(r'<li><a href=#([^>]+)>', content)
    section_headers = re.findall(r'^## (.+)$', content, re.MULTILINE)
    expected = {topic_anchor(h) for h in section_headers}

    assert toc_anchors, "TOC anchors should be present"
    for anchor in toc_anchors:
        assert anchor in expected, (
            f"TOC anchor #{anchor!r} has no matching section header. "
            f"Available section anchors: {expected}"
        )


def test_render_readme_back_to_top_anchor_matches_top_header(populated_data_dir, tmp_path):
    """The 'back to top' link points at the auto-generated anchor for the top H2 header."""
    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")

    from render_readme import topic_anchor
    top_header = re.search(r'^## (Updated on .+)$', content, re.MULTILINE)
    assert top_header is not None
    expected = topic_anchor(top_header.group(1))

    back_to_top_anchors = re.findall(r'<a href=#([^>]+)>back to top</a>', content)
    assert back_to_top_anchors, "back-to-top links should be present"
    for a in back_to_top_anchors:
        assert a == expected, f"back-to-top anchor #{a} != section anchor #{expected}"


def test_render_readme_multi_topic_paper_shown_in_both(populated_data_dir, tmp_path):
    """A paper with two topics appears in both topic sections."""
    import data_io
    by_month, _ = data_io.load_all_months()
    by_month["2025-04"]["2504.00001"]["topics"] = ["Topic A", "Topic B"]
    data_io.save_month(by_month, "2025-04")

    out = tmp_path / "README.md"
    _run_render_readme(out)
    content = out.read_text(encoding="utf-8")
    # 2504.00001 should appear twice: once under Topic A, once under Topic B
    assert content.count("2504.00001") >= 2
