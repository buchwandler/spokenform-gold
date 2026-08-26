import unittest

from spokenform_gold.conflicts import find_conflicts, unresolved_adjudicated_conflicts


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

    def test_contextual_adjudication_does_not_remain_unresolved(self):
        conflict = {"key": ["de-DE", "ordinal", "1."]}
        adjudication = {
            "groups": [
                {
                    "key": ["de-DE", "ordinal", "1."],
                    "disposition": "contextual_valid",
                }
            ]
        }
        self.assertEqual(unresolved_adjudicated_conflicts([conflict], adjudication), [])

    def test_missing_adjudication_fails_closed(self):
        conflict = {"key": ["de-DE", "fraction", "3/4"]}
        unresolved = unresolved_adjudicated_conflicts([conflict], {"groups": []})
        self.assertEqual(unresolved[0]["action"], "missing_or_unresolved_adjudication")

    def test_unapplied_correction_fails_closed(self):
        conflict = {"key": ["de-DE", "chemical", "C₆H₁₂O₆"]}
        adjudication = {
            "groups": [
                {
                    "key": ["de-DE", "chemical", "C₆H₁₂O₆"],
                    "disposition": "corrected_policy_inconsistency",
                }
            ]
        }
        unresolved = unresolved_adjudicated_conflicts([conflict], adjudication)
        self.assertEqual(unresolved[0]["action"], "correction_not_applied")


if __name__ == "__main__":
    unittest.main()
