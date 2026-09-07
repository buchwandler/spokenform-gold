import unittest

from spokenform_gold.review_anomaly import build_review_anomaly_report


class ReviewAnomalyTests(unittest.TestCase):
    def test_uniform_no_change_packet_requires_fresh_review(self):
        rows = [
            {
                "case_id": f"case-{index}",
                "language": "lt",
                "input": f"Value {index}",
                "annotation": {
                    "status": "no_change",
                    "units": [],
                    "oracle": {"canonical_output": f"Value {index}"},
                },
            }
            for index in range(10)
        ]
        sources = [{"units": [{"source_category": "Version Numbers"}]} for _ in rows]
        report = build_review_anomaly_report(rows, source_rows=sources, slot="A")
        codes = {signal["code"] for signal in report["signals"]}
        self.assertFalse(report["ready"])
        self.assertTrue(report["fresh_review_required"])
        self.assertIn("uniform_status", codes)
        self.assertIn("uniform_no_change_normalization_packet", codes)
        self.assertIn("canonical_output_always_equals_input", codes)

    def test_small_heterogeneous_packet_is_clean(self):
        rows = [
            {"case_id": "case-a", "input": "hello", "annotation": {"status": "gold"}},
            {
                "case_id": "case-b",
                "input": "world",
                "annotation": {"status": "no_change"},
            },
        ]
        report = build_review_anomaly_report(rows, slot="B")
        self.assertTrue(report["ready"])
        self.assertFalse(report["signals"])


if __name__ == "__main__":
    unittest.main()
