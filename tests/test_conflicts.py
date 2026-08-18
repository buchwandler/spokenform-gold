import unittest

from spokenform_gold.conflicts import find_conflicts


class ConflictTests(unittest.TestCase):
    def test_unit_conflict(self):
        first = {
            "locale": "en-US",
            "status": "gold",
            "input": "x 3/4",
            "source": {"benchmark": "a"},
            "units": [
                {
                    "surface": "3/4",
                    "category": "fraction",
                    "canonical": "three quarters",
                    "accepted": ["three quarters"],
                }
            ],
        }
        second = {
            "locale": "en-US",
            "status": "gold",
            "input": "x 3/4",
            "source": {"benchmark": "b"},
            "units": [
                {
                    "surface": "3/4",
                    "category": "fraction",
                    "canonical": "three slash four",
                    "accepted": ["three slash four"],
                }
            ],
        }
        conflicts = find_conflicts([first, second], "unit")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["key"], ["en-US", "fraction", "3/4"])
        self.assertEqual(conflicts[0]["action"], "needs_adjudication")


if __name__ == "__main__":
    unittest.main()
