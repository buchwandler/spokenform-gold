import unittest

from spokenform_gold.source_manifest import build_source_materialization_census


class SourceManifestTests(unittest.TestCase):
    def test_materialization_census_groups_records_and_manifest_policy(self):
        records = [
            {
                "id": "one",
                "source_observations": [
                    {
                        "benchmark": "fixture",
                        "source_version": "rev-1",
                        "source_id": "fixture:1",
                        "materialization": "embedded",
                    }
                ],
            },
            {
                "id": "two",
                "source_observations": [
                    {
                        "benchmark": "fixture",
                        "source_version": "rev-1",
                        "source_id": "fixture:2",
                        "materialization": "embedded",
                    }
                ],
            },
        ]
        census = build_source_materialization_census(
            records,
            {
                "sources": [
                    {
                        "name": "fixture",
                        "materialization_policy": "embedded_public",
                        "release_ready": True,
                        "license": "CC-BY-4.0",
                        "redistribution_status": "allowed",
                    }
                ]
            },
        )
        self.assertEqual(census["records_checked"], 2)
        self.assertEqual(len(census["groups"]), 1)
        self.assertEqual(census["groups"][0]["records"], 2)
        self.assertEqual(census["groups"][0]["unique_source_ids"], 2)
        self.assertEqual(census["groups"][0]["manifest_policy"], "embedded_public")
        self.assertTrue(census["groups"][0]["release_ready"])


if __name__ == "__main__":
    unittest.main()
