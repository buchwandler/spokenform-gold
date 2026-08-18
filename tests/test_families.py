import unittest

from spokenform_gold.families import sentence_skeleton, suggest_families


def candidate(
    record_id,
    source_id,
    text,
    units,
    language="en",
    locale="en-US",
    benchmark="async_tn",
):
    return {
        "id": record_id,
        "input": text,
        "language": language,
        "locale": locale,
        "source": {"benchmark": benchmark, "source_id": source_id},
        "units": units,
    }


class FamilySuggestionTests(unittest.TestCase):
    def test_sentence_skeleton_replaces_spans(self):
        item = candidate(
            "a",
            "1",
            "The event is on 05/20/2023.",
            [
                {
                    "surface": "05/20/2023",
                    "start": 16,
                    "end": 26,
                    "category": "date",
                    "features": {"surface_pattern": "slash_date"},
                }
            ],
        )
        self.assertEqual(sentence_skeleton(item), "the event is on <date>.")

    def test_parallel_source_templates_are_grouped_for_review(self):
        units = [
            {
                "surface": "09:30",
                "start": 12,
                "end": 17,
                "category": "time",
                "features": {"surface_pattern": "leading_zero_time"},
            }
        ]
        records = [
            candidate("de", "curated-1:de", "Treffen um 09:30.", units, "de", "de-DE"),
            candidate("en", "curated-1:en", "Meeting at 09:30.", units),
        ]
        suggestions = suggest_families(records)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(set(suggestions[0]["members"]), {"de", "en"})
        self.assertTrue(suggestions[0]["requires_review"])

    def test_different_contexts_are_not_merged(self):
        unit_a = [
            {
                "surface": "3-2",
                "start": 14,
                "end": 17,
                "category": "score_or_range",
                "features": {"surface_pattern": "score"},
            }
        ]
        unit_b = [
            {
                "surface": "3-2",
                "start": 13,
                "end": 16,
                "category": "score_or_range",
                "features": {"surface_pattern": "numeric_range"},
            }
        ]
        records = [
            candidate("a", "1", "The score was 3-2.", unit_a),
            candidate("b", "2", "The range is 3-2.", unit_b),
        ]
        self.assertEqual(len(suggest_families(records)), 2)


if __name__ == "__main__":
    unittest.main()
