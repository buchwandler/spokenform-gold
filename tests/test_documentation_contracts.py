import unittest
from pathlib import Path

from spokenform_gold.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_documented_workflow_commands_exist(self):
        help_text = build_parser().format_help()
        for command in (
            "review-preflight",
            "validate-review",
            "doctor",
            "prepare-canonical-rereview",
            "compare-reviews",
            "apply-reviewed-oracles",
            "adjudication-check",
            "review-report",
            "trace-record",
            "prepare-correction",
            "apply-correction",
        ):
            self.assertIn(command, help_text)

    def test_canonical_templates_contain_safety_invariants(self):
        canonical = (
            ROOT / "templates/canonical-rereview-adjudicator-task.md"
        ).read_text()
        for text in (
            "review-preflight",
            "canonical records do not store sentence_oracle_id",
            "stop if ready=no",
            "do not inspect source evidence before preflight",
        ):
            self.assertIn(text, canonical)
        reviewer = (ROOT / "templates/reviewer-ab-task.md").read_text()
        self.assertIn("validate-review", reviewer)
        self.assertIn(".complete.jsonl", reviewer)

    def test_canonical_artifact_names_and_schemas_are_documented(self):
        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "docs/ORACLE_REVIEW.md",
            ROOT / "templates/README.md",
            ROOT / "spokenform-gold-template-review-and-release-runbook.md",
        ]
        combined = "\n".join(path.read_text() for path in paths)
        for name in (
            "canonical-a.blind.jsonl",
            "canonical-a.complete.jsonl",
            "canonical-b.blind.jsonl",
            "canonical-b.complete.jsonl",
            "preflight.json",
            "comparison.jsonl",
            "decisions.jsonl",
            "manifest.json",
            "schemas/canonical-review-decision.schema.json",
        ):
            self.assertIn(name, combined)
        self.assertTrue(
            (ROOT / "templates/canonical-rereview-integration-task.md").exists()
        )

    def test_human_review_contract_is_documented(self):
        paths = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "templates/batch-handoff.md", ROOT / "spokenform-gold-template-review-and-release-runbook.md"]
        combined = "\n".join(path.read_text() for path in paths)
        for text in ("review-report.html", "record.id", "A/B disagreement", "needs_review", "do not ask the human", "JSONL"):
            self.assertIn(text, combined)


    def test_canonical_records_do_not_require_persisted_identity(self):
        records = list((ROOT / "data/test").glob("*.jsonl"))
        self.assertTrue(records)
        for path in records:
            for line in path.read_text().splitlines():
                if line.strip():
                    self.assertNotIn('"sentence_oracle_id"', line)


    def test_sentence_centric_v2_workflow_is_primary(self):
        primary_paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "templates/README.md",
            ROOT / "templates/coding-agent-first-task.md",
            ROOT / "spokenform-gold-template-review-and-release-runbook.md",
        ]
        combined = "\n".join(path.read_text() for path in primary_paths)
        self.assertIn("collect -> review-check -> adjudicate -> integrate -> validate -> report", combined)
        self.assertIn("data/corpus.jsonl", combined)
        self.assertIn("--limit 1000", combined)
        self.assertIn('review_schema_version: "2.0.0"', combined)
        self.assertIn("Compatibility-only", combined)
        self.assertNotIn("review-batch as the primary", combined)
        self.assertNotIn("train/dev/test authoring", combined)

        coding_template = (ROOT / "templates/coding-agent-first-task.md").read_text()
        primary_section = coding_template.split("## Compatibility-only workflows", 1)[0]
        for legacy_command in ("blind-review", "promote-reviewed", "--batch-limit 100"):
            self.assertNotIn(legacy_command, primary_section)

    def test_v2_reviewer_contract_is_documented(self):
        reviewer = (ROOT / "templates/reviewer-ab-task.md").read_text()
        for text in (
            'review_schema_version: "2.0.0"',
            "case_id",
            "schemas/review.schema.json",
            "a.complete.jsonl",
            "b.complete.jsonl",
            'review.status: "unreviewed"',
            "Large-batch checkpointing",
            "partial",
            "full case-ID set",
        ):
            self.assertIn(text, reviewer)
        self.assertIn("Compatibility-only legacy path", reviewer)
        self.assertNotIn("sentence_oracle_id", reviewer)

    def test_v2_adjudicator_contract_is_documented(self):
        adjudicator = (ROOT / "templates/adjudicator-task.md").read_text()
        for text in (
            "cases.jsonl",
            "context.jsonl",
            "adjudicated.jsonl",
            "schemas/adjudication.schema.json",
            "final_record",
            "accept",
            "exclude",
            "unresolved",
            "Large-batch checkpointing",
            "adjudicated.partial.jsonl",
            "complete batch case-ID set",
        ):
            self.assertIn(text, adjudicator)
        self.assertIn("Compatibility-only legacy candidate path", adjudicator)


if __name__ == "__main__":
    unittest.main()
