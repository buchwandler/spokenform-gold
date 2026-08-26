import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentContextBudgetTests(unittest.TestCase):
    def test_agents_file_has_bounded_size(self):
        path = ROOT / "AGENTS.md"
        text = path.read_text()
        self.assertLessEqual(len(text), 12_000)
        self.assertLessEqual(len(text.splitlines()), 300)

    def test_agents_file_routes_context_safely(self):
        text = (ROOT / "AGENTS.md").read_text()
        for phrase in (
            "Never recursively grep or search `.`",
            "Never cat, recursively grep, or full-read `data/corpus/`",
            "20,000 output characters",
            "bounded by case count and serialized",
            "Do not preload repository documentation",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("Read this first", text)
        self.assertNotIn("data/train", text)
        self.assertNotIn("data/dev", text)
        self.assertNotIn("data/test", text)

    def test_obsolete_templates_are_absent(self):
        for name in (
            "canonical-rereview-adjudicator-task.md",
            "canonical-rereview-integration-task.md",
            "promote-split-commit-task.md",
        ):
            self.assertFalse((ROOT / "templates" / name).exists())


if __name__ == "__main__":
    unittest.main()
