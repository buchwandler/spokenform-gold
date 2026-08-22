import unittest

from spokenform_gold.exclusions import build_exclusion_analysis, infer_surface_shape
from spokenform_gold.pool import build_candidate_pool_summary


class ExclusionTests(unittest.TestCase):
    def test_surface_shapes_and_grouping(self):
        self.assertEqual(infer_surface_shape("192.168.0.1"), "ipv4")
        result = build_exclusion_analysis(
            [
                {
                    "source": "async_tn",
                    "reason": "bad",
                    "source_category": "date",
                    "language": "en",
                    "detail": "03/04/2025",
                },
                {
                    "source": "async_tn",
                    "reason": "bad",
                    "source_category": "date",
                    "language": "en",
                    "detail": "03/04/2025",
                },
            ]
        )
        self.assertEqual(result["exclusions"], 2)
        self.assertEqual(result["groups"][0]["surface_shape"], "date")
        self.assertEqual(result["groups"][0]["count"], 2)

    def test_pool_summary_contains_required_statistics(self):
        records = [
            {
                "id": "one",
                "input": "A 1",
                "language": "en",
                "source": {"benchmark": "async_tn"},
                "units": [
                    {
                        "category": "cardinal",
                        "mapping_status": "exact",
                        "features": {"surface_pattern": "digits"},
                    }
                ],
            },
            {
                "id": "two",
                "input": "No change",
                "language": "de",
                "source": {"benchmark": "polynorm"},
                "units": [],
            },
        ]
        result = build_candidate_pool_summary(
            records,
            exclusions=[
                {
                    "source": "async_tn",
                    "reason": "bad",
                    "source_category": "date",
                    "language": "en",
                    "detail": "03/04/2025",
                }
            ],
            import_reports=[
                {
                    "source": "async_tn",
                    "source_rows": 4,
                    "records_created": 3,
                    "exclusions": 1,
                    "metadata_only_records": 1,
                    "row_accounting_ok": True,
                }
            ],
            conflicts=[{"id": "conflict"}],
        )
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["unique_inputs"], 2)
        self.assertEqual(result["metadata_only_records"], 1)
        self.assertEqual(result["multi_unit_records"], 0)
        self.assertEqual(result["conflicting_output_groups"], 1)
        for key in (
            "sources",
            "languages",
            "categories",
            "surface_patterns",
            "mapping_status",
            "source_yields",
            "exclusions_by_source",
            "exclusions_by_reason",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["source_yields"]["async_tn"]["yield"], 0.75)
        self.assertEqual(result["exclusions_by_reason"], {"bad": 1})
        self.assertEqual(result["exclusions_by_source"], {"async_tn": 1})


if __name__ == "__main__":
    unittest.main()
