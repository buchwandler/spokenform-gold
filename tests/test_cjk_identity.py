import unittest

from spokenform_gold.collection import cluster_observations
from spokenform_gold.corpus import (
    IdentityCollisionError,
    exact_surface_hash,
    find_identity_collisions,
    migrate_record,
    stable_record_id,
)
from spokenform_gold.io import read_records


class CjkIdentityTests(unittest.TestCase):
    def test_nfkc_compatibility_surfaces_are_reported(self):
        pairs = [
            ("１", "1"),
            ("ｶﾀｶﾅ", "カタカナ"),
            ("Ⅳ", "IV"),
            ("①", "1"),
            ("㎏", "kg"),
        ]
        for left, right in pairs:
            records = [
                {"id": "left", "language": "ja", "locale": "ja-JP", "input": left},
                {"id": "right", "language": "ja", "locale": "ja-JP", "input": right},
            ]
            collisions = find_identity_collisions(records)
            self.assertEqual(len(collisions), 1, (left, right))
            self.assertEqual(collisions[0]["record_ids"], ["left", "right"])
            self.assertEqual(len(collisions[0]["exact_surface_hashes"]), 2)

    def test_whitespace_normalization_is_not_a_compatibility_collision(self):
        records = [
            {"language": "en", "locale": "en-US", "input": "Value 3/4."},
            {"language": "en", "locale": "en-US", "input": "Value  3/4."},
        ]
        self.assertEqual(find_identity_collisions(records), [])
        self.assertEqual(cluster_observations(records)[0]["input"], "Value 3/4.")

    def test_collection_rejects_compatibility_collision(self):
        records = [
            {"language": "zh", "locale": "zh-CN", "input": "编号１"},
            {"language": "zh", "locale": "zh-CN", "input": "编号1"},
        ]
        with self.assertRaisesRegex(IdentityCollisionError, "identity collision"):
            cluster_observations(records)

    def test_exact_surface_hash_does_not_normalize(self):
        self.assertNotEqual(exact_surface_hash("１"), exact_surface_hash("1"))

    def test_existing_record_id_algorithm_remains_legacy_stable(self):
        record = read_records(["data/corpus.jsonl"])[0]
        self.assertEqual(migrate_record(record)["id"], record["id"])
        self.assertEqual(
            stable_record_id({"language": "ja", "locale": "ja-JP", "input": "１"}),
            stable_record_id({"language": "ja", "locale": "ja-JP", "input": "1"}),
        )


if __name__ == "__main__":
    unittest.main()
