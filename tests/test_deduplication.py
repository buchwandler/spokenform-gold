import unittest

from spokenform_gold.deduplication import (
    deduplicate_candidates,
    normalize_for_fingerprint,
)


def record(record_id, benchmark, source_id, text, expected):
    return {
        "id": record_id,
        "input": text,
        "source": {
            "benchmark": benchmark,
            "source_id": source_id,
            "source_version": "v1",
            "upstream_expected": expected,
        },
    }


class DeduplicationTests(unittest.TestCase):
    def test_duplicate_lineage_and_conflict_groups(self):
        records = [
            record(
                "a",
                "async_tn",
                "1",
                "The date is 03/04/2025.",
                "March fourth twenty twenty five.",
            ),
            record(
                "p",
                "polynorm",
                "en-US:1",
                " the date is 03/04/2025. ",
                "March fourth twenty twenty five.",
            ),
            record(
                "x",
                "proteno_en",
                "2",
                "The date is 03/04/2025.",
                "April third twenty twenty five.",
            ),
        ]
        result = deduplicate_candidates(records)
        self.assertEqual(result["records"], 3)
        self.assertEqual(len(result["exact_input_groups"]), 1)
        self.assertEqual(len(result["exact_pair_groups"]), 1)
        self.assertEqual(len(result["conflicting_output_groups"]), 1)
        members = result["exact_input_groups"][0]["members"]
        self.assertEqual({item["source_id"] for item in members}, {"1", "en-US:1", "2"})
        self.assertEqual(
            result["source_overlap_counts"],
            {
                "async_tn:polynorm": 1,
                "async_tn:proteno_en": 1,
                "polynorm:proteno_en": 1,
            },
        )

    def test_fingerprints_are_deterministic(self):
        self.assertEqual(normalize_for_fingerprint(" A  B "), "a b")
        records = [
            record("b", "b", "2", "Text", "Output"),
            record("a", "a", "1", "Text", "Output"),
        ]
        self.assertEqual(
            deduplicate_candidates(records),
            deduplicate_candidates(list(reversed(records))),
        )


if __name__ == "__main__":
    unittest.main()
