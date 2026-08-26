import tempfile
import unittest
from pathlib import Path

from spokenform_gold.packets import (
    PacketError,
    adjudication_packet_rows,
    finalize_adjudication,
    merge_adjudication_rows,
    merge_review_rows,
    review_packet_rows,
    serialized_row_bytes,
)


def blind_row(index: int, slot: str = "A") -> dict:
    return {
        "review_schema_version": "2.0.0",
        "case_id": f"case-{index:04d}",
        "reviewer_slot": slot,
        "language": "en",
        "locale": "en-US",
        "input": f"Value {index}.",
        "family_id": f"family-{index}",
        "annotation": None,
        "review": {"status": "unreviewed"},
    }


def complete_row(index: int, slot: str = "A") -> dict:
    row = blind_row(index, slot)
    row["reviewer_id"] = f"reviewer-{slot.lower()}"
    row["annotation"] = {
        "status": "gold",
        "expected_output": row["input"],
        "units": [],
        "negative_for": [],
        "notes": "test",
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


class PacketTests(unittest.TestCase):
    def test_reviewer_packets_are_bounded_and_resume_in_stable_order(self):
        rows = [blind_row(index) for index in range(1000)]
        packet_a = review_packet_rows(rows, max_cases=200, max_bytes=100_000)
        packet_b = review_packet_rows(
            rows,
            packet_a,
            max_cases=200,
            max_bytes=100_000,
        )
        self.assertEqual(len(packet_a), 200)
        self.assertEqual(len(packet_b), 200)
        self.assertEqual(packet_a[0]["case_id"], "case-0000")
        self.assertEqual(packet_b[0]["case_id"], "case-0200")
        self.assertLessEqual(
            sum(serialized_row_bytes(row) for row in packet_a), 100_000
        )
        self.assertEqual(
            {row["case_id"] for row in packet_a} & {row["case_id"] for row in packet_b},
            set(),
        )
        for row in packet_a:
            self.assertNotIn("source_observations", row)
            self.assertNotIn("upstream_expected", row)
            self.assertNotIn("current_output", row)

    def test_reviewer_merge_is_atomic_idempotent_and_rejects_conflicts(self):
        blind = [blind_row(0)]
        result = [complete_row(0)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "a.complete.jsonl"
            merged = merge_review_rows(blind, [], result, slot="A", output=output)
            self.assertEqual(merged, result)
            self.assertEqual(merge_review_rows(blind, merged, result, slot="A"), result)
            conflicting = complete_row(0)
            conflicting["annotation"]["notes"] = "conflict"
            with self.assertRaisesRegex(PacketError, "conflicting duplicate"):
                merge_review_rows(blind, merged, [conflicting], slot="A")
            self.assertEqual(len(output.read_text().splitlines()), 1)

    def test_adjudication_projection_aligns_sources_and_resumes(self):
        cases = [
            {
                **blind_row(index),
                "source_observations": [{"source_id": f"source-{index}"}],
            }
            for index in range(3)
        ]
        contexts = [{**case, "extra_context": True} for case in cases]
        review_a = [complete_row(index, "A") for index in range(3)]
        review_b = [complete_row(index, "B") for index in range(3)]
        packet = adjudication_packet_rows(
            cases,
            contexts,
            review_a,
            review_b,
            [{"case_id": "case-0000"}],
            max_cases=2,
            max_bytes=100_000,
        )
        self.assertEqual([row["case_id"] for row in packet], ["case-0001", "case-0002"])
        for row in packet:
            self.assertEqual(row["case"]["case_id"], row["context"]["case_id"])
            self.assertEqual(row["review_a"]["case_id"], row["review_b"]["case_id"])
            self.assertNotIn("source_observations", row["case"])
            self.assertNotIn("source_observations", row["context"])
            self.assertEqual(len(row["source_observations"]), 1)

    def test_adjudication_merge_requires_one_identity_and_exact_finalize_set(self):
        decisions = [
            {
                "case_id": "case-0",
                "adjudicator_id": "adj",
                "decision": "exclude",
                "rationale": "duplicate",
            },
            {
                "case_id": "case-1",
                "adjudicator_id": "adj",
                "decision": "exclude",
                "rationale": "policy",
            },
        ]
        merged = merge_adjudication_rows([], decisions)
        self.assertEqual([row["case_id"] for row in merged], ["case-0", "case-1"])
        self.assertEqual(
            finalize_adjudication(
                [{"case_id": "case-0"}, {"case_id": "case-1"}], merged
            ),
            merged,
        )
        with self.assertRaisesRegex(PacketError, "stable adjudicator"):
            merge_adjudication_rows(
                merged,
                [{**decisions[0], "case_id": "case-2", "adjudicator_id": "other"}],
            )
        with self.assertRaisesRegex(PacketError, "case-ID set mismatch"):
            finalize_adjudication([{"case_id": "case-0"}], merged)

    def test_single_oversized_case_fails_explicitly(self):
        row = blind_row(0)
        row["input"] = "x" * 600_000
        with self.assertRaisesRegex(PacketError, "case-0000.*max byte budget"):
            review_packet_rows([row], max_cases=1, max_bytes=98_304)


if __name__ == "__main__":
    unittest.main()
