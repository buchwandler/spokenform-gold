from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "pages.yml"


def test_pages_workflow_checks_out_corpus_before_uploading() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    checkout = workflow.index("actions/checkout@v4")
    upload = workflow.index("actions/upload-pages-artifact@v3")

    assert checkout < upload
    assert "path: docs/corpus" in workflow
    assert '".github/workflows/pages.yml"' in workflow
