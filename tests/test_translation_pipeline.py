import tempfile
import unittest
from pathlib import Path

from spokenform_gold.collection import blind_case, collect_batch
from spokenform_gold.corpus import read_corpus
from spokenform_gold.io import read_records, write_jsonl
from spokenform_gold.review import validate_v2_review_rows
from spokenform_gold.translation import (
    build_translation_tasks,
    finalize_translations,
)
from spokenform_gold.validation import validate_records
from spokenform_gold.workflow import check_reviews, integrate_batch


class TranslationPipelineTests(unittest.TestCase):
    @staticmethod
    def _translation_row(task, slot, translator_id, target_input):
        return {
            **task,
            "translator_slot": slot,
            "translator_id": translator_id,
            "translation": {
                "decision": "propose",
                "transfer_relation": "adapted",
                "target_input": target_input,
            },
            "review": {"status": "completed"},
        }

    @staticmethod
    def _semantic_review(case, slot, reviewer_id):
        row = blind_case(case, slot)
        row["reviewer_id"] = reviewer_id
        row["annotation"] = {
            "status": "no_change",
            "expected_output": row["input"],
            "units": [],
            "negative_for": ["date"],
            "oracle": {
                "canonical_output": row["input"],
                "accepted_outputs": [row["input"]],
                "rejected_outputs": [],
            },
        }
        row["review"] = {
            "status": f"review_{slot.lower()}_complete",
            "protocol_version": "2.0.0",
        }
        return row

    def test_finalized_candidate_uses_ordinary_v2_pipeline(self):
        source = read_corpus("data/corpus")[1]
        task = build_translation_tasks(
            [source], target_language="ja", target_locale="ja-JP"
        )[0]
        translation_a = self._translation_row(
            task, "A", "translator-a", "会議は三月十四日です。"
        )
        translation_b = self._translation_row(
            task, "B", "translator-b", "会議は3月14日です。"
        )
        decision = {
            "translation_case_id": task["translation_case_id"],
            "adjudicator_id": "translation-adjudicator",
            "decision": "accept_a",
            "selection": "A",
            "rationale": "Natural Japanese locale transplant.",
            "final_translation": translation_a["translation"],
        }
        candidates = finalize_translations(
            [task], [translation_a], [translation_b], [decision]
        )
        self.assertEqual(candidates[0]["source"]["benchmark"], "spokenform_translation")
        self.assertEqual(candidates[0]["source"]["translation_relation"], "adapted")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations = root / "candidates.jsonl"
            write_jsonl(observations, candidates)
            batch_root = root / "batch"
            collect_batch(
                [observations], output_root=batch_root, batch_id="ja-smoke", limit=1
            )
            case = read_records([batch_root / "cases.jsonl"])[0]
            self.assertEqual(case["language"], "ja")
            self.assertEqual(case["family_id"], source["family_id"])
            review_a = self._semantic_review(case, "A", "semantic-a")
            review_b = self._semantic_review(case, "B", "semantic-b")
            self.assertTrue(check_reviews([case], [review_a], [review_b])["ready"])
            self.assertTrue(validate_v2_review_rows([review_a], slot="A")["ready"])
            write_jsonl(batch_root / "a.complete.jsonl", [review_a])
            write_jsonl(batch_root / "b.complete.jsonl", [review_b])
            write_jsonl(
                batch_root / "adjudicated.jsonl",
                [
                    {
                        "case_id": case["case_id"],
                        "adjudicator_id": "gold-adjudicator",
                        "decision": "accept",
                        "rationale": "Independent semantic review passed.",
                        "final_record": {
                            "taxonomy_version": "1.0.0",
                            "policy_version": "1.0.0",
                            "family_id": case["family_id"],
                            "status": "no_change",
                            "input": case["input"],
                            "units": [],
                            "negative_for": ["date"],
                            "notes": "Smoke-test target-language negative control.",
                            "oracle": {
                                "canonical_output": case["input"],
                                "variant_mode": "explicit",
                                "accepted_outputs": [case["input"]],
                                "rejected_outputs": [],
                            },
                        },
                    }
                ],
            )
            target = root / "corpus.jsonl"
            result = integrate_batch(batch_root, target, write=True)
            self.assertEqual(result["records"], 1)
            self.assertEqual(validate_records(read_records([target])), [])
            integrated = read_records([target])[0]
            self.assertEqual(
                integrated["source_observations"][0]["translation_parent_record_id"],
                source["id"],
            )


if __name__ == "__main__":
    unittest.main()
