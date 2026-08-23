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

Compare two genuinely independent completed reviewer artifacts for the existing canonical corpus, resolve semantic disagreements under Spokenform Gold policy, and emit one complete canonical-oracle decision for every derived `sentence_oracle_id`.

Canonical records do **not** store a `sentence_oracle_id` field. The repository derives the review identity from language, locale, and normalized input. Never inspect `record["sentence_oracle_id"]` or recreate the hash in an ad-hoc script; use the supported CLI/API.
Plain contract: canonical records do not store sentence_oracle_id; it is derived for review artifacts only.

This workflow does not make a source-materialization decision, promote a candidate, assign a new family, change provenance, apply decisions, or change Gold because current Spokenform output differs. Existing canonical record ID, family ID, language, locale, input, and source identity remain unchanged.

## First gate: preflight before inspection

Replace placeholders with a task instance manifest before starting. New canonical artifacts use these names:

```text
reviews/canonical/canonical-a.blind.jsonl
reviews/canonical/canonical-a.complete.jsonl
reviews/canonical/canonical-b.blind.jsonl
reviews/canonical/canonical-b.complete.jsonl
reviews/canonical/preflight.json
reviews/canonical/comparison.jsonl
reviews/canonical/decisions.jsonl
reviews/canonical/manifest.json
```

Allowed policy/schema inputs are exactly: `AGENTS.md`, `README.md`, `DATA_MODEL.md`, `docs/ANNOTATION.md`, `docs/ORACLE_REVIEW.md`, `docs/SOURCE_POLICY.md`, `taxonomy/categories.json`, `taxonomy/coverage_targets.json`, `schemas/oracle.schema.json`, `schemas/completed-review-row.schema.json`, and `schemas/canonical-review-decision.schema.json`.

Run exactly this readiness command first, before reading source evidence, Git history, candidate decisions, release artifacts, current canonical oracle values, or Spokenform output:

```bash
spokenform-gold review-preflight \
  --records <ABSOLUTE_PATHS_TO_DATA_TRAIN_DEV_TEST> \
  --review-a <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_A_COMPLETE_JSONL> \
  --review-b <ABSOLUTE_PATH_TO_CANONICAL_REVIEW_B_COMPLETE_JSONL> \
  --json <ABSOLUTE_PATH_TO_PREFLIGHT_JSON>
```

If `ready=no`, report the aggregate summary and artifact hashes, then stop immediately. stop if ready=no; do not inspect source evidence before preflight:

1. do not inspect semantic source evidence;
2. do not run `compare-reviews`, adjudication, release, or audit commands;
3. do not search for alternative review files unless the task manifest names them;
4. do not invent reviewer IDs, repair reviews, or inspect current implementation output.

A blocked run means no comparison or decision artifact was produced. A ready run must show both distinct stable reviewer IDs, complete annotations and lifecycle states, exact A/B ID parity, context parity, and canonical derived-identity parity before continuing.

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
