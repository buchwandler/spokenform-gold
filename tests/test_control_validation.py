import unittest

from spokenform_gold.control_validation import validate_control_records


def control_record(**overrides):
    record = {
        "schema_version": "1.0.0",
        "id": "control-001",
        "family_id": "family-001",
        "control": "sequence_fallback_mode",
        "language": "en",
        "locale": "en-US",
        "input": "AAPL",
        "source": {
            "benchmark": "spokenform_curated",
            "source_id": "control-001",
            "source_version": "0.3.0-control-review",
            "source_url": "https://example.invalid/spokenform-gold",
            "license": "CC-BY-4.0",
        },
        "expectations": [
            {
                "profile_id": "gold-v1",
                "expected_output": "AAPL",
                "required_rules": [],
                "forbidden_rules": ["fallback.sequence"],
            }
        ],
        "notes": "Residual sequence is preserved by the canonical profile.",
    }
    record.update(overrides)
    return record


class ControlValidationTests(unittest.TestCase):
    def test_valid_control_record(self):
        self.assertEqual(validate_control_records([control_record()]), [])

    def test_unknown_profile_fails_closed(self):
        record = control_record()
        record["expectations"][0]["profile_id"] = "missing"
        errors = validate_control_records([record])
        self.assertTrue(any("unknown profile_id" in error for error in errors))

    def test_arbitrary_runtime_kwargs_are_rejected(self):
        record = control_record(prepare_kwargs={"sequence_fallback_mode": "spell"})
        errors = validate_control_records([record])
        self.assertTrue(any("runtime kwargs" in error for error in errors))

    def test_required_and_forbidden_rules_must_be_disjoint(self):
        record = control_record()
        record["expectations"][0]["required_rules"] = ["protected"]
        record["expectations"][0]["forbidden_rules"] = ["protected"]
        errors = validate_control_records([record])
        self.assertTrue(any("overlap" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
