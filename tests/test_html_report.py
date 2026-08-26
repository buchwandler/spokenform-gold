from pathlib import Path

from spokenform_gold.html_report import render_release_html


def test_release_html_is_self_contained_filterable_and_escaped(tmp_path: Path):
    record = {
        "id": 'record-<script>alert("x")</script>',
        "family_id": "family-1",
        "split": "test",
        "language": "en",
        "locale": "en-US",
        "status": "gold",
        "input": "Value < 3",
        "expected_output": "Value less than three",
        "oracle": {
            "canonical_output": "Value less than three",
            "accepted_outputs": ["Value less than three"],
            "rejected_outputs": [],
        },
        "source": {"benchmark": "spokenform_curated"},
        "review": {"status": "release_ready"},
        "units": [
            {
                "surface": "< 3",
                "category": "math_expression",
                "canonical": "less than three",
                "semantic": {"operator": "<", "right": 3},
                "policy": "math-natural",
            }
        ],
    }
    output = render_release_html(
        tmp_path / "records.html",
        version="1.0.0",
        maturity="candidate",
        records=[record],
        coverage={"gaps": []},
        control_coverage={"gaps": []},
        counts={"families": 1},
    )
    text = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert 'data-filter="language"' in text
    assert 'class="record-row"' in text
    assert "record-&lt;script&gt;" in text
    assert '<script>alert("x")</script>' not in text
    assert "https://" not in text
    assert "cdn" not in text.lower()


def test_release_html_exposes_translation_lineage(tmp_path: Path):
    record = {
        "id": "sfg-ja-1",
        "family_id": "family-1",
        "language": "ja",
        "locale": "ja-JP",
        "status": "no_change",
        "input": "会議です。",
        "oracle": {
            "canonical_output": "会議です。",
            "accepted_outputs": ["会議です。"],
            "rejected_outputs": [],
        },
        "units": [],
        "source_observations": [
            {
                "benchmark": "spokenform_translation",
                "translation_parent_record_id": "parent-1",
                "translation_relation": "adapted",
            }
        ],
    }
    output = render_release_html(
        tmp_path / "translation.html",
        version="1.0.0",
        maturity="experimental",
        records=[record],
        coverage={"gaps": []},
        control_coverage={"gaps": []},
        counts={"families": 1},
    )
    text = output.read_text(encoding="utf-8")
    assert "translation-derived" in text
    assert "parent-1" in text
    assert "adapted" in text
