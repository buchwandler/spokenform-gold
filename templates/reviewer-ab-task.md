# Independent Reviewer A/B — Fresh-Context Task Template

> Run this template in two separate, isolated contexts: once for slot A and once
> for slot B. Replace every `<PLACEHOLDER>` before handing it to a reviewer.

---

You are independent reviewer **<A_OR_B>** for Spokenform Gold batch
**<BATCH_ID>**.

## Goal

Complete every row in the explicit blind preparation artifact without consulting upstream
expected outputs, current Spokenform behavior, the other reviewer, or an
adjudication result:

```text
<ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_OR_B_BLIND_JSONL>
```

Write the completed reviewer artifact to a new `.complete.jsonl` file; never overwrite the `.blind.jsonl` input:

```text
<ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_OR_B_COMPLETE_JSONL>
```

Use this stable, truthful reviewer identity in every row:

```text
<REVIEWER_ID>
```

Do not invent an identity or claim independence if another person or agent
supplied your semantic answers.

## Repository policy available to you

You may read only the following policy/schema files plus your blind artifact:

```text
AGENTS.md
README.md
DATA_MODEL.md
docs/ANNOTATION.md
docs/ORACLE_REVIEW.md
docs/SOURCE_POLICY.md
docs/ROADMAP.md
taxonomy/coverage_targets.json
taxonomy/categories.json
taxonomy/policies.json
taxonomy/ambiguity_families.json
schemas/oracle.schema.json
schemas/oracle-review.schema.json
schemas/record.schema.json
```

Do **not** inspect candidate files, source caches, source expected outputs,
Spokenform code/output, another review file, comparison files, or decisions.
Do not search the web for the source sentence.

The benchmark policy defines Gold; the current implementation does not. Canonical records do not store `sentence_oracle_id`; the review identity is derived from language, locale, and normalized input and must be preserved exactly from the blind artifact.

## Input contract

Each input row represents one sentence-oracle cluster and contains:

```text
review_schema_version
sentence_oracle_id
reviewer_slot
language
locale
input
materialization
source_refs
annotation: null
review.status: unreviewed
```

Multiple source candidates can share one sentence-oracle row. Review the
sentence and locale, not the source's preferred answer. Do not alter
`sentence_oracle_id`, input, language, locale, materialization, or source refs.

Before annotating, verify:

1. every row has your assigned `reviewer_slot`;
2. every annotation is null;
3. no row contains `upstream_expected`, `upstream_output`, `current_output`,
   `spokenform_output`, or another completed annotation;
4. the output path differs from the input path.

Stop and report the problem if any check fails.

## Required semantic review

For every row, independently determine:

1. exact normalization spans using zero-based, end-exclusive offsets;
2. canonical taxonomy category for each span;
3. machine-readable semantics;
4. whether the sentence is genuinely ambiguous;
5. registered policy ID;
6. canonical unit realization;
7. explicit meaning-preserving unit variants;
8. plausible but wrong unit variants;
9. canonical full-sentence output;
10. explicit accepted full-sentence outputs;
11. rejected full-sentence outputs and reasons;
12. nearby false-positive risk and whether this row should remain unchanged.

Do not guess missing context. Use an ambiguity status when the sentence itself
cannot determine one interpretation. Do not silently repair the source text.

## Completed row shape

Preserve all input fields and add `reviewer_id`. Replace `annotation: null` with
this shape:

```json
{
  "review_schema_version": "1.0.0",
  "sentence_oracle_id": "<PRESERVE>",
  "reviewer_slot": "<A_OR_B>",
  "reviewer_id": "<REVIEWER_ID>",
  "language": "<PRESERVE>",
  "locale": "<PRESERVE>",
  "input": "<PRESERVE>",
  "materialization": "<PRESERVE>",
  "source_refs": [{ "benchmark": "<PRESERVE>", "source_id": "<PRESERVE>" }],
  "annotation": {
    "status": "gold",
    "expected_output": "Canonical full sentence.",
    "units": [
      {
        "surface": "3/4",
        "start": 4,
        "end": 7,
        "category": "fraction",
        "semantic": { "numerator": 3, "denominator": 4 },
        "policy": "<REGISTERED_POLICY_ID>",
        "canonical": "three quarters",
        "accepted": ["three quarters", "three fourths"],
        "rejected": ["three slash four"],
        "features": { "surface_pattern": "numeric_fraction" }
      }
    ],
    "negative_for": [],
    "notes": "Independent semantic-review rationale.",
    "oracle": {
      "canonical_output": "Canonical full sentence.",
      "accepted_outputs": ["Canonical full sentence."],
      "rejected_outputs": [
        { "output": "Wrong full sentence.", "reason": "Changes the meaning." }
      ],
      "variant_mode": "explicit",
      "comparison_profile": "sentence-exact-v1"
    }
  },
  "review": {
    "status": "review_a_complete",
    "protocol_version": "1.0.0"
  }
}
```

For slot B use `review_b_complete`. The example values are illustrative only;
do not copy them into unrelated rows.

Status guidance:

- `gold`: one clear reviewed interpretation;
- `multi_valid`: multiple policy-equivalent spoken realizations;
- `policy_choice`: policy deliberately chooses among plausible conventions;
- `ambiguous`: context does not determine one interpretation;
- `no_change`: input must remain unchanged, `units == []`,
  `expected_output == input`, and `negative_for` is non-empty.

For reviewed non-ambiguous rows:

```text
annotation.expected_output == annotation.oracle.canonical_output
oracle.canonical_output must occur in oracle.accepted_outputs
unit.canonical must occur in unit.accepted
unit.accepted and unit.rejected must be disjoint
```

Accepted sentence outputs are explicit. Do not infer an unchecked Cartesian
product from unit variants.

## Mechanical checks before handoff

Confirm locally that:

- output is valid JSONL with one object per line;
- row count and `sentence_oracle_id` set match the blank artifact;
- every row has the same non-empty reviewer ID;
- every annotation is complete;
- lifecycle status matches your slot;
- preserved context fields are byte-for-byte unchanged;
- forbidden blind fields are absent.

Run the independent artifact check before handoff:

```bash
spokenform-gold validate-review <ABSOLUTE_PATH_TO_COMPLETE_JSONL> --slot <A_OR_B>
```

Do not run `compare-reviews`; that step requires both independent artifacts and
belongs to the adjudication context.

## Handoff

Report only:

```text
batch ID
reviewer slot and reviewer ID
input and output artifact paths
row count
ambiguous count
no-change count
rows flagged in notes for adjudication
mechanical checks performed
```

Do not include or request the other reviewer's answers.
