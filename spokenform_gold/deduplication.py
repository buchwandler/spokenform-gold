from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations

from .io import sha256_text


def normalize_for_fingerprint(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _member(record: dict, input_fingerprint: str, pair_fingerprint: str) -> dict:
    source = record.get("source", {})
    return {
        "record_id": record.get("id"),
        "benchmark": source.get("benchmark"),
        "source_id": source.get("source_id"),
        "source_version": source.get("source_version"),
        "input_fingerprint": input_fingerprint,
        "pair_fingerprint": pair_fingerprint,
    }


def _grouped(records: Iterable[dict], key_name: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record[key_name]].append(record)
    output = []
    for fingerprint, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        output.append(
            {
                "fingerprint": fingerprint,
                "members": sorted(
                    members,
                    key=lambda item: (
                        item.get("source", {}).get("benchmark", ""),
                        item.get("source", {}).get("source_id", ""),
                        item.get("id", ""),
                    ),
                ),
            }
        )
    return output


def deduplicate_candidates(records: Iterable[dict]) -> dict:
    prepared = []
    for record in sorted(records, key=lambda item: item.get("id", "")):
        normalized_input = normalize_for_fingerprint(record.get("input"))
        upstream = normalize_for_fingerprint(
            record.get("source", {}).get("upstream_expected")
            or record.get("expected_output")
        )
        input_fingerprint = sha256_text(normalized_input)
        pair_fingerprint = sha256_text(normalized_input + "\x1f" + upstream)
        prepared.append(
            {
                "record": record,
                "input_fingerprint": input_fingerprint,
                "pair_fingerprint": pair_fingerprint,
                "normalized_upstream": upstream,
            }
        )

    exact_input_groups = []
    exact_pair_groups = []
    by_input: dict[str, list[dict]] = defaultdict(list)
    by_pair: dict[str, list[dict]] = defaultdict(list)
    for item in prepared:
        member = _member(
            item["record"], item["input_fingerprint"], item["pair_fingerprint"]
        )
        by_input[item["input_fingerprint"]].append(member)
        by_pair[item["pair_fingerprint"]].append(member)
    for fingerprint, members in sorted(by_input.items()):
        if len(members) > 1:
            exact_input_groups.append({"fingerprint": fingerprint, "members": members})
    for fingerprint, members in sorted(by_pair.items()):
        if len(members) > 1:
            exact_pair_groups.append({"fingerprint": fingerprint, "members": members})

    conflicting_output_groups = []
    for fingerprint, items in sorted(
        ((key, value) for key, value in by_input.items()), key=lambda pair: pair[0]
    ):
        source_outputs = defaultdict(list)
        for item in prepared:
            if item["input_fingerprint"] == fingerprint:
                source_outputs[item["normalized_upstream"]].append(
                    _member(item["record"], fingerprint, item["pair_fingerprint"])
                )
        outputs = [output for output in source_outputs if output]
        if len(outputs) > 1:
            conflicting_output_groups.append(
                {
                    "input_fingerprint": fingerprint,
                    "outputs": [
                        {"normalized_output": output, "members": source_outputs[output]}
                        for output in sorted(outputs)
                    ],
                    "action": "needs_adjudication",
                }
            )

    source_overlap_counts: dict[str, int] = defaultdict(int)
    for group in exact_input_groups:
        benchmarks = sorted(
            {member.get("benchmark", "") for member in group["members"]}
        )
        for left, right in combinations(benchmarks, 2):
            source_overlap_counts[f"{left}:{right}"] += 1

    return {
        "records": len(prepared),
        "unique_input_fingerprints": len(by_input),
        "unique_pair_fingerprints": len(by_pair),
        "exact_input_groups": exact_input_groups,
        "exact_pair_groups": exact_pair_groups,
        "conflicting_output_groups": conflicting_output_groups,
        "source_overlap_counts": dict(sorted(source_overlap_counts.items())),
    }
