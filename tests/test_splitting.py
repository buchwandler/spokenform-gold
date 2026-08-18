import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.splitting import load_split_registry, split_records


class SplittingTests(unittest.TestCase):
    def test_split_is_registry_backed_and_family_safe(self):
        records = [
            {"id": "a1", "family_id": "fam-a", "split": "dev"},
            {"id": "a2", "family_id": "fam-a", "split": "dev"},
            {"id": "b1", "family_id": "fam-b", "split": "test"},
            {"id": "c1", "family_id": "fam-c", "split": "candidate"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = Path(tmpdir) / "family_assignments.json"
            first = split_records(records, registry_path=registry, seed=7)
            second = split_records(records, registry_path=registry, seed=7)
            self.assertEqual(first, second)
            locations = {}
            for split_name, split_records_list in first.items():
                for record in split_records_list:
                    locations.setdefault(record["family_id"], set()).add(split_name)
            self.assertTrue(
                all(len(split_names) == 1 for split_names in locations.values())
            )
            saved = load_split_registry(registry)
            self.assertEqual(saved["families"]["fam-a"], "dev")
            self.assertEqual(saved["families"]["fam-b"], "test")

    def test_adding_new_families_does_not_move_existing_assignments(self):
        base_records = [
            {"id": "a1", "family_id": "fam-a", "split": "dev"},
            {"id": "b1", "family_id": "fam-b", "split": "test"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = Path(tmpdir) / "family_assignments.json"
            split_records(base_records, registry_path=registry, seed=20260818)
            before = json.loads(registry.read_text(encoding="utf-8"))
            expanded = base_records + [
                {"id": "c1", "family_id": "fam-c", "split": "candidate"}
            ]
            split_records(expanded, registry_path=registry, seed=20260818)
            after = json.loads(registry.read_text(encoding="utf-8"))
            self.assertEqual(before["families"]["fam-a"], after["families"]["fam-a"])
            self.assertEqual(before["families"]["fam-b"], after["families"]["fam-b"])
            self.assertIn("fam-c", after["families"])

    def test_seed_mismatch_is_rejected_for_existing_registry(self):
        records = [{"id": "a1", "family_id": "fam-a", "split": "dev"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = Path(tmpdir) / "family_assignments.json"
            split_records(records, registry_path=registry, seed=1)
            with self.assertRaises(ValueError):
                split_records(records, registry_path=registry, seed=2)


if __name__ == "__main__":
    unittest.main()
