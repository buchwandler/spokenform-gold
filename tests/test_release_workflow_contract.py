from pathlib import Path


def test_release_workflow_uses_decisions_and_verifies_preflight():
    workflow = (
        Path(__file__)
        .parents[1]
        .joinpath(".github", "workflows", "release.yml")
        .read_text()
    )
    assert (
        workflow.count("--source-decisions release/source-release-decisions.json") >= 2
    )
    assert "--release-sources spokenform_curated" not in workflow
    assert 'report["accounted"] != report["canonical_records"]' in workflow
    assert 'report["blocked"] != 0' in workflow
