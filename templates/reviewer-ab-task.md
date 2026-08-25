# Independent Reviewer A/B, Sentence-Centric v2

> Run this template twice, once in a distinct fresh context for slot A and once in a distinct fresh context for slot B. Replace every placeholder with truthful values.

## Role and isolation

You are independent reviewer **<A_OR_B>** for batch **<BATCH_ID>**. Use the stable truthful identity **<REVIEWER_ID>** in every output row.

Read only the reviewer policy and schema files named below plus your assigned blind artifact:

```text
AGENTS.md
README.md
DATA_MODEL.md
docs/ANNOTATION.md
docs/SOURCE_POLICY.md
taxonomy/categories.json
taxonomy/policies.json
schemas/review.schema.json
schemas/record.schema.json
<ABSOLUTE_PATH_TO_<A_OR_B>.blind.jsonl>
```

Do not inspect `context.jsonl`, source candidates, source caches, upstream expected outputs, current Spokenform output, the other review, comparison files, adjudication files, or the web. Do not claim independence if your context saw another reviewer’s answers or hidden source evidence.

## Input and output

Input:

```text
<ABSOLUTE_PATH_TO_<A_OR_B>.blind.jsonl>
```

Write a new completed artifact. Never overwrite the blind artifact:

```text
<ABSOLUTE_PATH_TO_a.complete.jsonl> for slot A
<ABSOLUTE_PATH_TO_b.complete.jsonl> for slot B
```

`collect` emits one row per sentence case with exactly this v2 preparation contract:

```text
review_schema_version: "2.0.0"
case_id
reviewer_slot
language
locale
input
family_id
annotation: null
review.status: "unreviewed"
```

Preserve `case_id`, `language`, `locale`, `input`, `family_id`, and `reviewer_slot` byte-for-byte. Add `reviewer_id`, replace `annotation: null` with your independent review, and set `review.status` to the completed slot-specific value. Preserve no hidden source evidence because none belongs in the blind row.

## Independent semantic review

For every case, determine independently:

1. exact zero-based, end-exclusive normalization spans;
2. taxonomy category for every span;
3. machine-readable semantics;
4. whether the sentence is genuinely ambiguous;
5. the registered policy ID;
6. canonical unit realization;
7. explicit meaning-preserving unit variants;
8. plausible but wrong unit variants;
9. canonical full-sentence output;
10. explicit accepted full-sentence outputs;
11. rejected full-sentence outputs and reasons;
12. nearby false-positive risk and whether the sentence is a `no_change` control.

Do not guess missing context. Use an ambiguity status when the sentence does not determine one interpretation. Do not silently repair the input.

For reviewed non-ambiguous rows, ensure:

```text
annotation.expected_output == annotation.oracle.canonical_output
annotation.oracle.canonical_output is in annotation.oracle.accepted_outputs
unit.canonical is in unit.accepted
unit.accepted and unit.rejected are disjoint
```

For `no_change`, use `expected_output == input`, `units == []`, and a non-empty `negative_for` list.

## Completed row requirements

Each completed row must remain a valid `schemas/review.schema.json` row and contain:

```json
{
  "review_schema_version": "2.0.0",
  "case_id": "<PRESERVE>",
  "reviewer_slot": "<A_OR_B>",
  "reviewer_id": "<REVIEWER_ID>",
  "language": "<PRESERVE>",
  "locale": "<PRESERVE>",
  "input": "<PRESERVE>",
  "family_id": "<PRESERVE>",
  "annotation": {
    "status": "gold",
    "expected_output": "Canonical full sentence.",
    "units": [],
    "negative_for": [],
    "notes": "Independent semantic-review rationale.",
    "oracle": {
      "canonical_output": "Canonical full sentence.",
      "accepted_outputs": ["Canonical full sentence."],
      "rejected_outputs": [],
      "variant_mode": "explicit",
      "comparison_profile": "sentence-exact-v1"
    }
  },
  "review": {
    "status": "review_a_complete",
    "protocol_version": "2.0.0"
  }
}
```

Use `review_b_complete` for slot B. The example values are illustrative and must not be copied into unrelated cases.

## Mechanical handoff

Before handoff, verify:

- output is valid JSONL with one object per line;
- row count and case ID set match the blind artifact;
- every row has the same non-empty truthful reviewer ID;
- every row has the assigned slot;
- every annotation is complete and no annotation is null;
- preserved fields are unchanged;
- no forbidden source or implementation output fields are present.

Run:

```bash
spokenform-gold validate-review <ABSOLUTE_PATH_TO_<A_OR_B>.complete.jsonl> --slot <A_OR_B>
```

Do not run `compare-reviews`; that belongs to the adjudication context after both reviews are complete.

Report only the batch ID, slot and reviewer ID, input/output paths, row count, ambiguity and no-change counts, rows flagged for adjudication, and mechanical checks performed. Do not include the other reviewer’s answers.

## Compatibility-only legacy path

The repository still supports legacy canonical re-review artifacts for compatibility. That path may use its separately documented derived identity and canonical rereview schemas, but it is not the v2 data-growth contract above. Do not mix legacy fields or lifecycle names into a v2 `collect` batch.
