import unittest

from spokenform_gold.splitting import split_records


class SplittingTests(unittest.TestCase):
    def test_split_is_deterministic_and_family_safe(self):
        records = [
            {"id": "a1", "family_id": "fam-a", "split": "dev"},
            {"id": "a2", "family_id": "fam-a", "split": "dev"},
            {"id": "b1", "family_id": "fam-b", "split": "dev"},
            {"id": "c1", "family_id": "fam-c", "split": "dev"},
        ]
        first = split_records(records, train_ratio=0.5, dev_ratio=0.25, test_ratio=0.25, seed=7)
        second = split_records(records, train_ratio=0.5, dev_ratio=0.25, test_ratio=0.25, seed=7)
        self.assertEqual(first, second)
        locations = {}
        for split_name, split_records_list in first.items():
            for record in split_records_list:
                locations.setdefault(record["family_id"], set()).add(split_name)
        self.assertTrue(all(len(split_names) == 1 for split_names in locations.values()))


if __name__ == "__main__":
    unittest.main()
