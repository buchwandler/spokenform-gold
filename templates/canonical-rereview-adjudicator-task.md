# Canonical Re-review Adjudicator — Fresh-Context Task Template

> Use this role only for existing canonical records (or records already admitted
> to canonical review). It is not the candidate-promotion adjudicator. Replace
> every `<PLACEHOLDER>` before starting.

---

You are the canonical sentence-oracle re-review adjudicator for **<REVIEW_ID>**.

Use this stable, truthful adjudicator identity:

```text
<ADJUDICATOR_ID>
```

## Goal and boundary

Compare two genuinely independent blind reviews of the existing canonical
corpus, resolve semantic disagreements under Spokenform Gold policy, and emit
one complete canonical-oracle decision for every `sentence_oracle_id`.

This workflow corrects or confirms reviewed semantics. It does **not** make a
source-materialization decision, promote a candidate, assign a new family, or
change provenance. The existing canonical record ID, family ID, language,
locale, input, and source identity must remain unchanged.

Do not choose an answer because it matches current Spokenform output. The
benchmark policy and semantic evidence define the result.

## Inputs and output

Provide only the files needed for this role:

```text
canonical records:       <ABSOLUTE_PATHS_TO_DATA_TRAIN_DEV_TEST>
completed review A:      <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_JSONL>
completed review B:      <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_B_JSONL>
comparison output:       <ABSOLUTE_PATH_TO_COMPARISON_JSONL>
allowed policy/schema:   <REPOSITORY_FILES_NAMED_BY_REVIEWER_TEMPLATE>
```

Write a new decision artifact; never overwrite the reviews or canonical data:

```text
<ABSOLUTE_PATH_TO_CANONICAL_DECISIONS_JSONL>
```

The decision artifact must contain exactly one decision for each canonical
`sentence_oracle_id`, with no duplicate IDs and no decisions for unknown
records.

## Required preflight

Run the comparison command before inspecting source evidence or making a final
decision:

```bash
spokenform-gold compare-reviews \
  <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_JSONL> \
  <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_B_JSONL> \
  --out <ABSOLUTE_PATH_TO_COMPARISON_JSONL>
```

Stop and hand off a blocker if this fails. Confirm that:

- reviewer A and B identities are non-empty and distinct;
- every row is complete and has the correct reviewer slot lifecycle state;
- the `sentence_oracle_id` sets match exactly;
- input, language, and locale match between reviewers and canonical records;
- neither review exposes upstream expectations or current Spokenform output;
- each canonical record maps to exactly one sentence-oracle identity;
- the comparison artifact is saved and its SHA256 is recorded.

Do not invent missing review evidence or silently repair a mismatched identity.

## Adjudication procedure

For each `sentence_oracle_id`:

1. inspect the comparison dimensions for span, category, semantic, ambiguity,
   policy, unit realization, accepted variants, sentence canonical output, and
   rejected variants;
2. inspect both independent rationales;
3. only when necessary, inspect existing source provenance as evidence; never
   replace the canonical source identity or upstream fields;
4. determine the final spans and machine-readable semantics under registered
   taxonomy and policy;
5. determine the canonical unit realization, explicitly accepted unit variants,
   and rejected variants;
6. determine the complete full-sentence oracle and its explicit accepted and
   rejected outputs;
7. record structured disagreement dimensions and source error codes;
8. preserve the existing record and family identity exactly;
9. choose `adjudicated` or `release_ready` as the final review lifecycle state;
10. run completeness checks before handing the artifact to the mechanical
    integration context.

If context remains genuinely insufficient, retain an explicit ambiguous or
otherwise non-gold semantic status rather than guessing. If a proposed result
would change source identity, family assignment, or canonical record identity,
stop and escalate it as a separate policy/migration task.

## Decision record contract

Each decision must be keyed by `sentence_oracle_id` and preserve these identity
fields from the canonical record:

```json
{
  "sentence_oracle_id": "<EXACT_CANONICAL_ORACLE_ID>",
  "record_id": "<EXACT_EXISTING_RECORD_ID>",
  "family_id": "<EXACT_EXISTING_FAMILY_ID>",
  "input": "<EXACT_EXISTING_INPUT>",
  "language": "<EXACT_EXISTING_LANGUAGE>",
  "locale": "<EXACT_EXISTING_LOCALE>",
  "reviewers": ["<REVIEWER_A_ID>", "<REVIEWER_B_ID>"],
  "adjudicator": "<ADJUDICATOR_ID>",
  "review_status": "adjudicated",
  "review_protocol_version": "1.0.0",
  "status": "gold",
  "expected_output": "Complete canonical sentence.",
  "units": [],
  "negative_for": [],
  "notes": "Policy-based adjudication rationale.",
  "oracle": {
    "canonical_output": "Complete canonical sentence.",
    "accepted_outputs": ["Complete canonical sentence."],
    "rejected_outputs": [],
    "variant_mode": "explicit",
    "comparison_profile": "sentence-exact-v1"
  },
  "disagreement": {},
  "source_error_codes": []
}
```

The example is illustrative. Populate `units` completely for positive records.
For `no_change`, require `expected_output == input`, `units == []`, and a
non-empty `negative_for`. For ambiguous records, use the repository's approved
status and explain the unresolved interpretation in `notes` and the oracle.

For every non-ambiguous decision, verify:

```text
expected_output == oracle.canonical_output
oracle.canonical_output is in oracle.accepted_outputs
unit.canonical is in unit.accepted for every unit
unit.accepted and unit.rejected are disjoint
oracle.accepted_outputs and oracle.rejected_outputs are disjoint
```

The full-sentence oracle is authoritative for sentence scoring. Do not derive
unchecked sentence variants from a Cartesian product of unit variants.

## Prohibited changes

- Do not emit candidate-promotion disposition records or license/materialization
  decisions.
- Do not change `record_id`, `family_id`, source provenance, input, language, or
  locale.
- Do not apply the decisions, copy files into `data/train`, `data/dev`, or
  `data/test`, split records, commit, tag, or publish.
- Do not edit taxonomy or policy files from the adjudicator context. Flag a
  missing policy/category for a separate policy decision.
- Do not fabricate reviewer identities or claim independent review.

## Handoff to mechanical application

Before handoff, verify:

- canonical record count equals decision count;
- canonical `sentence_oracle_id` set equals decision ID set;
- every decision has the exact existing record and family identity;
- reviewer pairs match the completed A/B artifacts;
- every decision has `status`, `expected_output`, `units`, `negative_for`,
  `notes`, and `oracle`;
- every review status is `adjudicated` or `release_ready`;
- all oracle and record invariants pass;
- no source identity or materialization field changed;
- SHA256 hashes are recorded for review A, review B, comparison, and decisions.

Hand off the decision artifact and evidence to a separate integration context.
That context alone may run:

```bash
spokenform-gold apply-reviewed-oracles \
  --records data/train data/dev data/test \
  --review-a <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_JSONL> \
  --review-b <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_B_JSONL> \
  --decisions <ABSOLUTE_PATH_TO_CANONICAL_DECISIONS_JSONL> \
  --out-root <ABSOLUTE_WORK_ROOT>/canonical-rereview
```

The integration context must use an isolated output tree, preserve the frozen
family split registry, inspect oracle diffs, validate the generated shards, and
obtain explicit approval before copying reviewed records into Git.

## Handoff report

Report only:

```text
review ID and canonical input paths
review A/B IDs and artifact paths
comparison and decision artifact paths
record and sentence-oracle counts
agreement/disagreement counts
adjudicated/release_ready/ambiguous/no_change counts
source error-code counts
artifact SHA256 values
mechanical checks performed
unresolved blockers
```
