import unittest

from spokenform_gold.ranking import export_review_batch


class ReviewBatchTests(unittest.TestCase):
    def _item(self, record_id, category, family, language="en", priority=100):
        return {
            "record_id": record_id,
            "priority": priority,
            "reasons": ["category_missing"],
            "language": language,
            "categories": [category],
            "family_id": family,
            "record": {
                "id": record_id,
                "status": "quarantine",
                "family_id": family,
                "language": language,
                "input": "Keep provenance",
                "source": {"benchmark": "async_tn", "source_id": record_id},
                "units": [{"category": category}],
            },
        }

    def test_batch_applies_limit_language_category_and_family_caps(self):
        items = [
            self._item("a", "date", "family-a", priority=100),
            self._item("b", "date", "family-a", priority=99),
            self._item("c", "phone", "family-c", language="de", priority=98),
            self._item("d", "email", "family-d", language="de", priority=97),
        ]
        batch = export_review_batch(
            items,
            limit=2,
            languages={"de"},
            max_per_category=1,
            max_per_family_suggestion=1,
        )
        self.assertEqual([record["id"] for record in batch], ["c", "d"])
        self.assertTrue(all(record["status"] == "quarantine" for record in batch))
        self.assertEqual(batch[0]["review_priority"], 98)
        self.assertEqual(batch[0]["review_reasons"], ["category_missing"])
        self.assertEqual(batch[0]["source"]["benchmark"], "async_tn")
        self.assertEqual(batch[0]["input"], "Keep provenance")


if __name__ == "__main__":
    unittest.main()
