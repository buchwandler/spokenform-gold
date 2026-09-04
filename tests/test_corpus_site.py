import json
from pathlib import Path

import pytest

from spokenform_gold.corpus_site import generate_corpus_site, render_corpus_site
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


def records():
    return read_records([ROOT / "data/test"])


def test_generates_language_index_pages_and_manifest(tmp_path):
    rows = records()
    result = generate_corpus_site(rows, tmp_path, write=True)
    assert result["files"] >= 4
    assert (tmp_path / "index.html").is_file()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["record_count"] == len(rows)
    assert set(manifest["languages"]) == {row["language"] for row in rows}
    for row in rows:
        hits = sum(
            f'id="record-{row["id"]}"' in path.read_text()
            for path in tmp_path.rglob("*.html")
        )
        assert hits == 1


def test_issue_action_and_source_observation_filter_are_generated():
    rows = records()
    rows[0]["source_observations"] = [{"benchmark": "async_tn"}]
    files = render_corpus_site(rows)
    pages = "".join(value for name, value in files.items() if name.endswith(".html"))
    assert "Report issue" in pages
    assert "URLSearchParams" in pages
    assert "async_tn" in pages
    without_issues = render_corpus_site(records(), issues_url=None)
    assert 'data-report-issue="' not in "".join(without_issues.values())


def test_site_is_deterministic_and_check_detects_stale_output(tmp_path):
    rows = records()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_corpus_site(rows, first, write=True)
    generate_corpus_site(rows, second, write=True)
    assert {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert generate_corpus_site(rows, first, check=True)["corpus_site"] == "current"
    (first / "index.html").write_text("stale", encoding="utf-8")
    stale = generate_corpus_site(rows, first, check=True)
    assert stale["corpus_site"] == "stale"
    assert stale["changed"] == 1


def test_refuses_invalid_corpus():
    row = records()[0]
    row["status"] = "ambiguous"
    row["units"][0]["category"] = "date"
    row["units"][0]["mapping_status"] = "ambiguous"
    row["units"][0]["semantic"] = {}
    with pytest.raises(ValueError, match="invalid corpus"):
        render_corpus_site([row])


def test_large_language_uses_parts_and_routing(tmp_path):
    rows = records()
    language_rows = [row for row in rows if row["language"] == "en"]
    generated = generate_corpus_site(
        language_rows, tmp_path, max_records_per_page=1, write=True
    )
    assert (tmp_path / "en" / "index.html").is_file()
    assert (tmp_path / "en" / "routing.json").is_file()
    assert generated["files"] > 3
    routing = json.loads((tmp_path / "en" / "routing.json").read_text())
    assert set(routing) == {row["id"] for row in language_rows}
    assert "location.replace" in (tmp_path / "en" / "index.html").read_text()
