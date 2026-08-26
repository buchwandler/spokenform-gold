import tempfile
import unittest
from pathlib import Path

from spokenform_gold.safe_search import search_text


class AgentSearchTests(unittest.TestCase):
    def test_defaults_exclude_data_indexes_and_bound_lines_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spokenform_gold" / "source.py"
            source.parent.mkdir()
            source.write_text("needle " + "x" * 600_000 + "\n", encoding="utf-8")
            (root / "context_spokenform_gold.index.json").write_text(
                "needle\n", encoding="utf-8"
            )
            data = root / "data"
            data.mkdir()
            (data / "corpus.jsonl").write_text('{"input":"needle"}\n', encoding="utf-8")

            result = search_text("needle", root=root)
            self.assertLessEqual(len(result), 20_000)
            self.assertIn("spokenform_gold/source.py:1:", result)
            self.assertNotIn("context_spokenform_gold", result)
            self.assertNotIn("corpus.jsonl", result)
            content = result.split(":", 2)[2].rstrip("\n")
            self.assertLessEqual(len(content), 500)

            included = search_text("needle", root=root, include_data=True)
            self.assertIn("data/corpus.jsonl", included)
            self.assertLessEqual(len(included), 20_000)

    def test_match_and_output_limits_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spokenform_gold" / "source.py"
            source.parent.mkdir()
            source.write_text(
                "\n".join(f"needle {i}" for i in range(20)), encoding="utf-8"
            )
            result = search_text("needle", root=root, max_matches=3, max_output=100)
            self.assertEqual(
                result,
                "spokenform_gold/source.py:1:needle 0\n"
                "spokenform_gold/source.py:2:needle 1\n"
                "spokenform_gold/source.py:",
            )


if __name__ == "__main__":
    unittest.main()
