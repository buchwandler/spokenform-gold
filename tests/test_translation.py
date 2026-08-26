import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.packets import PacketError
from spokenform_gold.translation import (
    TranslationLicenseError,
    build_translation_tasks,
    check_translation_batch,
    finalize_translations,
    merge_translation_adjudication_rows,
    merge_translation_rows,
    prepare_translation_batch,
    translation_adjudication_packet_rows,
    translation_blind_row,
    translation_packet_rows,
)


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = read_records(["data/corpus.jsonl"])[1]

    def _task(self):
        return build_translation_tasks(
            [self.record], target_language="ja", target_locale="ja-JP"
        )[0]

    @staticmethod
    def _completed(task, slot, translator_id, target_input):
        return {
            **task,
            "translator_slot": slot,
            "translator_id": translator_id,
            "translation": {
                "decision": "propose",
                "transfer_relation": "adapted",
                "target_input": target_input,
                "target_status_proposal": "gold",
                "target_oracle_proposal": {},
                "target_units_proposal": [],
                "target_negative_for_proposal": [],
                "notes": "independent test proposal",
            },
            "review": {"status": "completed"},
        }

    def test_prepare_is_deterministic_and_blinds_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            first = prepare_translation_batch(
                [self.record],
                directory,
                target_language="ja",
                target_locale="ja-JP",
                batch_id="tr-ja-0001",
            )
            self.assertEqual(first["case_count"], 1)
            root = Path(directory)
            a = read_records([root / "a.blind.jsonl"])[0]
            b = read_records([root / "b.blind.jsonl"])[0]
            self.assertEqual(a["source_record_id"], b["source_record_id"])
            self.assertEqual(a["source_oracle_hash"], b["source_oracle_hash"])
            self.assertEqual(a["translator_slot"], "A")
            self.assertEqual(b["translator_slot"], "B")
            self.assertNotIn("current_output", a)
            self.assertEqual(
                first["case_count"], len(read_records([root / "tasks.jsonl"]))
            )

    def test_packets_resume_and_merge_are_deterministic(self):
        task = self._task()
        a_blank = [translation_blind_row(task, "A")]
        packet = translation_packet_rows(a_blank, max_cases=1, max_bytes=10000)
        self.assertEqual(len(packet), 1)
        a = self._completed(task, "A", "translator-a", "会議は三月十四日です。")
        merged = merge_translation_rows(a_blank, [], [a], slot="A")
        self.assertEqual(merged, [a])
        self.assertEqual(merge_translation_rows(a_blank, merged, [a], slot="A"), merged)
        with self.assertRaisesRegex(PacketError, "conflicting duplicate"):
            merge_translation_rows(
                a_blank,
                merged,
                [{**a, "translation": {**a["translation"], "notes": "different"}}],
                slot="A",
            )

    def test_translation_check_requires_distinct_ids_but_allows_disagreement(self):
        task = self._task()
        a = self._completed(task, "A", "translator-a", "会議は三月十四日です。")
        b = self._completed(task, "B", "translator-b", "会議は3月14日です。")
        report = check_translation_batch([task], [a], [b])
        self.assertTrue(report["ready"])
        self.assertEqual(report["target_input_disagreement_count"], 2)
        same = self._completed(task, "B", "translator-a", "会議は3月14日です。")
        self.assertFalse(check_translation_batch([task], [a], [same])["ready"])

    def test_adjudication_supports_accept_merge_exclude_unresolved_and_finalize(self):
        task = self._task()
        a = self._completed(task, "A", "translator-a", "会議は三月十四日です。")
        b = self._completed(task, "B", "translator-b", "会議は3月14日です。")
        packet = translation_adjudication_packet_rows(
            [task], [a], [b], max_cases=1, max_bytes=10000
        )
        self.assertEqual(packet[0]["translation_case_id"], task["translation_case_id"])
        decision = {
            "translation_case_id": task["translation_case_id"],
            "adjudicator_id": "translation-judge",
            "decision": "accept_a",
            "selection": "A",
            "rationale": "A is natural",
            "final_translation": a["translation"],
        }
        merged = merge_translation_adjudication_rows([], [decision])
        candidates = finalize_translations([task], [a], [b], merged)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["language"], "ja")
        self.assertEqual(
            candidate["source"]["translation_parent_record_id"],
            task["source_record_id"],
        )
        self.assertEqual(candidate["family_suggestion"], task["parent_family_id"])
        self.assertNotIn("oracle", candidate)

        for final_decision in ("exclude", "unresolved"):
            row = {**decision, "decision": final_decision, "selection": None}
            self.assertEqual(finalize_translations([task], [a], [b], [row]), [])

    def test_missing_decision_and_restricted_seed_fail_closed(self):
        task = self._task()
        a = self._completed(task, "A", "translator-a", "会議は三月十四日です。")
        b = self._completed(task, "B", "translator-b", "会議は3月14日です。")
        with self.assertRaisesRegex(PacketError, "case-ID set mismatch"):
            finalize_translations([task], [a], [b], [])
        restricted = {
            **self.record,
            "source_observations": [
                {"benchmark": "polynorm", "license_id": "CC-BY-NC-ND-4.0"}
            ],
        }
        with self.assertRaises(TranslationLicenseError):
            build_translation_tasks(
                [restricted], target_language="ja", target_locale="ja-JP"
            )

    def test_translation_schemas_are_json_contracts(self):
        for name in (
            "translation-task.schema.json",
            "translation-review.schema.json",
            "translation-decision.schema.json",
        ):
            schema = json.loads((Path("schemas") / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["type"], "object")
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )


if __name__ == "__main__":
    unittest.main()
