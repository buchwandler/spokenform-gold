from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_uses_decisions_and_verifies_preflight() -> None:
    workflow = workflow_text()
    assert (
        workflow.count("--source-decisions release/source-release-decisions.json") >= 2
    )
    assert "--release-sources spokenform_curated" not in workflow
    assert 'report["accounted"] != report["canonical_records"]' in workflow
    assert 'report["blocked"] != 0' in workflow


def test_dispatch_plans_version_without_manual_version() -> None:
    workflow = workflow_text()
    assert "workflow_dispatch:" in workflow
    assert "        version:\n" not in workflow
    assert "--tags-from-git" in workflow
    assert "scripts/next_release_version.py" in workflow
    assert '--github-output "$GITHUB_OUTPUT"' in workflow


def test_release_jobs_are_staged_and_serialized() -> None:
    workflow = workflow_text()
    assert "group: spokenform-gold-release" in workflow
    assert "cancel-in-progress: false" in workflow
    for job in (
        "  plan:",
        "  candidate:",
        "  consumer-gate:",
        "  publish:",
        "  verify-published:",
    ):
        assert job in workflow
    assert "needs: [plan, candidate]" in workflow
    assert "needs: [plan, candidate, consumer-gate]" in workflow
    assert "environment: release" in workflow


def test_candidate_is_built_once_and_uploaded() -> None:
    workflow = workflow_text()
    assert "run: make check" in workflow
    assert "spokenform-gold release-preflight" in workflow
    assert "spokenform-gold release \\" in workflow
    assert "scripts/package_release.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "builder_commit" in workflow
    assert "ref: ${{ needs.plan.outputs.builder_commit }}" in workflow


def test_consumer_gate_uses_real_spokenform_and_publish_uses_candidate() -> None:
    workflow = workflow_text()
    assert "repository: buchwandler/spokenform" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "benchmarks.spokenform_gold" in workflow
    assert "--gold-root" in workflow
    assert "--accept-upstream-licenses" in workflow
    assert 'gh release download "${TAG}"' in workflow
    assert "scripts/compare_release_candidate.py" in workflow
    assert "args=(release create" in workflow
    assert '--target "${BUILDER_COMMIT}"' in workflow
    assert 'gh release download "$TAG"' in workflow
    assert "verify-published:" in workflow
