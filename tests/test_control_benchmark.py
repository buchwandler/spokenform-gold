import unittest

from spokenform_gold.control_benchmark import (
    build_control_predictions,
    score_control_records,
)
from tests.test_control_validation import control_record


class ControlBenchmarkTests(unittest.TestCase):
    def test_control_scoring_separates_output_and_rule_contracts(self):
        record = control_record(
            expectations=[
                {
                    "profile_id": "gold-v1",
                    "expected_output": "AAPL",
                    "required_rules": [],
                    "forbidden_rules": ["fallback.sequence"],
                },
                {
                    "profile_id": "fallback-spell-0.3",
                    "expected_output": "A A P L",
                    "required_rules": ["fallback.sequence"],
                    "forbidden_rules": [],
                },
            ]
        )
        predictions = {
            record["id"]: {
                "id": record["id"],
                "profiles": {
                    "gold-v1": {"output": "AAPL", "rules": []},
                    "fallback-spell-0.3": {
                        "output": "A A P L",
                        "rules": ["fallback.sequence"],
                    },
                },
            }
        }
        summary = score_control_records([record], predictions)
        self.assertEqual(summary["cases"], 1)
        self.assertEqual(summary["expectations"], 2)
        self.assertEqual(summary["output_accuracy"], 1.0)
        self.assertEqual(summary["full_accuracy"], 1.0)
        self.assertEqual(summary["forbidden_rule_violations"], 0)
        self.assertEqual(summary["by_control"]["sequence_fallback_mode"]["expectations"], 2)

    def test_forbidden_rule_violation_is_reported(self):
        record = control_record()
        predictions = {
            record["id"]: {
                "profiles": {
                    "gold-v1": {
                        "output": "AAPL",
                        "rules": ["fallback.sequence"],
                    }
                }
            }
        }
        summary = score_control_records([record], predictions)
        self.assertEqual(summary["forbidden_rule_violations"], 1)
        self.assertEqual(summary["false_positive_control_failures"], 1)
        self.assertEqual(summary["full_accuracy"], 0.0)

    def test_builder_accepts_output_and_rule_objects(self):
        record = control_record(
            expectations=[
                {
                    "profile_id": "fallback-spell-0.3",
                    "expected_output": "A A P L",
                    "required_rules": ["fallback.sequence"],
                    "forbidden_rules": [],
                }
            ]
        )

        def prepare(text, language, locale, profile):
            return {"output": "A A P L", "owners": ["fallback.sequence"]}

        predictions = build_control_predictions([record], prepare)
        self.assertEqual(predictions[0]["profiles"]["fallback-spell-0.3"]["rules"], ["fallback.sequence"])


if __name__ == "__main__":
    unittest.main()
