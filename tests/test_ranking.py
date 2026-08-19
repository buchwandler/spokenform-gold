import unittest

from spokenform_gold.ranking import build_candidate_ranking


class RankingTests(unittest.TestCase):
    def _record(self, record_id, category, language="en", pattern="plain_decimal", units=1):
        return {
            "id": record_id,
            "language": language,
            "locale": f"{language}-US",
            "status": "quarantine",
            "family_id": f"family-{record_id}",
            "source": {"benchmark": "async_tn", "source_id": record_id},
            "input": "value 1",
            "units": [
                {
                    "category": category,
                    "mapping_status": "exact",
                    "features": {"surface_pattern": pattern},
                }
                for _ in range(units)
            ],
        }

    def test_missing_category_and_language_rank_above_existing_category(self):
        reviewed = [self._record("reviewed", "decimal")]
        missing = self._record("missing", "phone", language="de", pattern="phone")
        existing = self._record("existing", "decimal")
        ranked = build_candidate_ranking(
            [existing, missing],
            reviewed,
            targets={"languages": ["en", "de"], "categories": {"decimal": {"min_units": 20}}},
        )
        self.assertEqual(ranked[0]["record_id"], "missing")
        self.assertIn("category_missing", ranked[0]["reasons"])
        self.assertIn("new_language_for_category", ranked[0]["reasons"])

    def test_conflict_and_multi_unit_reasons_are_deterministic(self):
        candidate = self._record("conflict", "date", units=2)
        conflict = [{"items": [{"record_id": "conflict"}]}]
        first = build_candidate_ranking([candidate], [], conflicts=conflict)
        second = build_candidate_ranking([candidate], [], conflicts=conflict)
        self.assertEqual(first, second)
        self.assertIn("source_disagreement", first[0]["reasons"])
        self.assertIn("multi_unit", first[0]["reasons"])

    def test_metadata_only_is_penalized(self):
        record = self._record("metadata", "date")
        record["units"] = []
        ranked = build_candidate_ranking([record], [])
        self.assertIn("metadata_only", ranked[0]["reasons"])
        self.assertEqual(ranked[0]["record"]["status"], "quarantine")

    def test_dedupe_conflicting_outputs_raise_source_disagreement(self):
        candidate = self._record("dedupe-conflict", "date")
        dedupe = {
            "conflicting_output_groups": [
                {
                    "outputs": [
                        {"members": [{"record_id": "dedupe-conflict"}]}
                    ]
                }
            ]
        }
        ranked = build_candidate_ranking([candidate], [], dedupe=dedupe)
        self.assertIn("source_disagreement", ranked[0]["reasons"])
        self.assertEqual(ranked[0]["record"]["status"], "quarantine")



if __name__ == "__main__":
    unittest.main()
