import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_TEMPLATES = {
    "coding-agent-first-task.md",
    "reviewer-ab-task.md",
    "adjudicator-task.md",
    "integration-task.md",
    "correction-task.md",
    "release-publish-task.md",
    "batch-handoff.md",
    "translator-ab-task.md",
    "translation-adjudicator-task.md",
}
OBSOLETE_TEMPLATES = {
    "canonical-rereview-adjudicator-task.md",
    "canonical-rereview-integration-task.md",
    "promote-split-commit-task.md",
}


class DocumentationContractTests(unittest.TestCase):
    def test_active_template_inventory_is_v2_only(self):
        actual = {path.name for path in (ROOT / "templates").glob("*.md")}
        self.assertEqual(actual, ACTIVE_TEMPLATES | {"README.md"})
        readme = (ROOT / "templates/README.md").read_text()
        for name in ACTIVE_TEMPLATES:
            self.assertIn(name, readme)
        for name in OBSOLETE_TEMPLATES:
            self.assertNotIn(name, readme)

    def test_obsolete_templates_are_removed(self):
        for name in OBSOLETE_TEMPLATES:
            self.assertFalse((ROOT / "templates" / name).exists())

    def test_active_docs_use_v2_authoring_contract(self):
        paths = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "templates/README.md",
            ROOT / "templates/coding-agent-first-task.md",
            ROOT / "templates/reviewer-ab-task.md",
            ROOT / "templates/adjudicator-task.md",
            ROOT / "templates/integration-task.md",
            ROOT / "templates/correction-task.md",
            ROOT / "templates/release-publish-task.md",
            ROOT / "templates/batch-handoff.md",
            ROOT / "spokenform-gold-template-review-and-release-runbook.md",
        ]
        combined = "\n".join(path.read_text() for path in paths)
        self.assertIn(
            "prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report",
            combined,
        )
        self.assertIn("data/corpus/", combined)
        self.assertIn("--limit 1000", combined)
        self.assertIn('review_schema_version: "2.0.0"', combined)
        for obsolete_command in (
            "spokenform-gold promote-reviewed",
            "spokenform-gold blind-review",
            "spokenform-gold review-batch",
            "--batch-limit 100",
        ):
            self.assertNotIn(obsolete_command, combined)
        for obsolete_concept in (
            "sentence_oracle_id",
            "canonical rereview",
            "data/train",
            "data/dev",
            "data/test",
        ):
            self.assertNotIn(obsolete_concept, combined)

    def test_release_workflow_uses_v2_corpus_and_independent_profile(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("spokenform-gold release \\", workflow)
        self.assertIn("--data data/corpus/", workflow)
        self.assertIn('--coverage-profile "${COVERAGE_PROFILE}"', workflow)
        self.assertIn(
            "--conflict-adjudication release/conflict-adjudication.json", workflow
        )
        self.assertIn("--release-sources spokenform_curated", workflow)
        self.assertNotIn("--data data/train data/dev data/test", workflow)
        self.assertNotIn("--registry splits/family_assignments.json", workflow)
        self.assertNotIn('coverage_profile="${MATURITY}"', workflow)
        self.assertIn('*exp*) maturity="experimental"', workflow)

    def test_human_review_contract_is_documented(self):
        combined = "\n".join(
            (ROOT / path).read_text()
            for path in (
                "AGENTS.md",
                "README.md",
                "templates/batch-handoff.md",
                "spokenform-gold-template-review-and-release-runbook.md",
            )
        )
        for text in (
            "review-report.html",
            "record.id",
            "A/B",
            "needs_review",
            "Do not ask",
            "JSONL",
        ):
            self.assertIn(text, combined)


if __name__ == "__main__":
    unittest.main()
