# Sentence-Centric v2 Adjudicator

> Use only after two genuinely independent blind reviews are complete. Replace every placeholder with truthful values.

## Role and inputs

You are the separate adjudicator for batch **<BATCH_ID>**. Use stable truthful identity **<ADJUDICATOR_ID>**.

You may read:

```text
cases.jsonl
context.jsonl
<a.complete.jsonl>
<b.complete.jsonl>
taxonomy/*
relevant policy documentation
schemas/adjudication.schema.json
schemas/record.schema.json
schemas/oracle.schema.json
```

Do not alter the input artifacts. Do not invent missing reviewer evidence. The benchmark policy defines Gold, not the current Spokenform implementation or an upstream majority vote.

Write exactly one row per `case_id` to:

```text
<ABSOLUTE_PATH_TO_adjudicated.jsonl>
```

## Preflight

Before adjudicating, run:

```bash
spokenform-gold review-check \
  --batch <ABSOLUTE_PATH_TO_BATCH_ROOT> \
  --review-a <ABSOLUTE_PATH_TO_a.complete.jsonl> \
  --review-b <ABSOLUTE_PATH_TO_b.complete.jsonl> \
  --json <ABSOLUTE_PATH_TO_review-check.json>
```

Require `ready=true`, exact case coverage, correct slots, distinct stable reviewer IDs, non-null completed annotations, and no forbidden source or implementation output. Stop rather than filling missing review evidence.

## Large-batch checkpointing

A 1,000-case adjudication is one logical file contract. You may write `adjudicated.partial.jsonl` as a same-adjudicator checkpoint, but never hand it to integration.

- Keep one truthful adjudicator identity for every checkpoint.
- Preserve exactly one decision per case ID in the final artifact.
- The final `adjudicated.jsonl` must cover the complete batch case-ID set with no duplicates.
- Run the complete deterministic checks only after the final artifact is assembled.


## Adjudication procedure

For each case:

1. compare A and B across spans, categories, semantics, ambiguity, policy, unit variants, sentence canonical output, accepted outputs, and rejected outputs;
2. inspect both independent rationales;
3. inspect all source observations and upstream expectations only now;
4. resolve the semantic interpretation under policy, without majority voting;
5. preserve meaning-preserving accepted alternatives and useful rejected variants;
6. preserve every source observation and its materialization policy;
7. assign or confirm a stable Spokenform-owned `family_id`;
8. emit one `accept`, `exclude`, or `unresolved` row.

A/B disagreement alone is not an unresolved blocker. Use `unresolved` only when a named hard blocker prevents a defensible decision after evaluating policy and allowed evidence. Synthetic requests remain candidates for a future independent A/B batch and must not be accepted into Gold in this batch.

## Decision contract

The only allowed decisions are:

```text
accept
exclude
unresolved
```

Every row contains:

```json
{
  "case_id": "<EXACT_CASE_ID>",
  "adjudicator_id": "<ADJUDICATOR_ID>",
  "decision": "accept",
  "rationale": "Policy-based adjudication rationale.",
  "final_record": {}
}
```

For `accept`, `final_record` must be a complete v2 record compatible with `schemas/record.schema.json`. It must contain a permanent `id`, `family_id`, language, locale, input, status, units, `source_observations`, and a full explicit `oracle`. It must not contain `split`, a duplicate legacy `expected_output`, or a `sentence_oracle_id`. Preserve the canonical record invariants, including accepted/rejected disjointness and `oracle.canonical_output` in `oracle.accepted_outputs`.

For `exclude`, omit `final_record` and explain why the case should not enter Gold, such as source error, duplicate assertion, policy exclusion, or licensing restriction.

For `unresolved`, omit `final_record` and include a concrete blocker and attempted resolution:

```json
{
  "case_id": "<EXACT_CASE_ID>",
  "adjudicator_id": "<ADJUDICATOR_ID>",
  "decision": "unresolved",
  "rationale": "The remaining blocker after policy review.",
  "blocker_code": "<REGISTERED_BLOCKER>",
  "blocker_reason": "Concrete reason no defensible record can be emitted.",
  "attempted_resolution": "Policy and available evidence considered."
}
```

## Completeness and handoff

Before handoff, verify:

```text
adjudication row count == cases row count
adjudication case_id set == cases case_id set
no duplicate case_id decisions
accepted final_record objects are complete v2 records
no accepted final_record has split or sentence_oracle_id
no unresolved case is eligible for integration
all source observations are preserved
```

Run the available deterministic adjudication/integration checks before handoff. Do not run promotion, split, copy canonical files, or commit; those belong to the mechanical integration context.

Report batch and artifact paths, case and decision counts, A/B agreement/disagreement counts, adjudicator identity, blocker counts, source/materialization decisions, synthetic requests, and mechanical validation results. The human receives the generated HTML report rather than JSONL rows.

## Compatibility-only legacy candidate path

The repository retains legacy candidate adjudication and promotion schemas for compatibility. Those artifacts may use candidate IDs, promotion decisions, source disposition, and legacy oracle fields, but they are not the v2 `case_id`/`final_record` contract above. Do not mix the two workflows.
