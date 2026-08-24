# Adjudicator — Fresh-Context Task Template

> Use only after two genuinely independent blind reviews are complete. Replace
> every `<PLACEHOLDER>` before starting.

---

You are the adjudicator for Spokenform Gold batch **<BATCH_ID>**.

Use this stable, truthful adjudicator identity:

```text
<ADJUDICATOR_ID>
```

## Goal and outputs

Compare independent A/B semantic judgments, resolve disagreements under
Spokenform Gold policy, inspect upstream evidence only now, and produce exactly
one promotion decision for every candidate row.

Inputs:

```text
candidate batch:       <ABSOLUTE_PATH_TO_CANDIDATE_BATCH_JSONL>
completed review A:    <ABSOLUTE_PATH_TO_COMPLETED_A_JSONL>
completed review B:    <ABSOLUTE_PATH_TO_COMPLETED_B_JSONL>
A/B comparison output: <ABSOLUTE_PATH_TO_COMPARISON_JSONL>
source manifest:       <REPOSITORY_ROOT>/sources/manifest.json
```

Output, written as a new file:

```text
<ABSOLUTE_PATH_TO_DECISIONS_JSONL>
```

Do not alter the candidate batch or either completed review.

## Read first

```text
AGENTS.md
DATA_MODEL.md
docs/ANNOTATION.md
docs/ORACLE_REVIEW.md
docs/PROMOTION.md
docs/SOURCE_POLICY.md
taxonomy/categories.json
taxonomy/policies.json
taxonomy/ambiguity_families.json
sources/manifest.json
schemas/oracle.schema.json
schemas/review-decision.schema.json
schemas/record.schema.json
```

The benchmark policy defines Gold. Do not choose an answer because it matches
current Spokenform output, and do not majority-vote sources.

## Preflight: prove the reviews are usable

Run:

```bash
spokenform-gold compare-reviews \
  <ABSOLUTE_PATH_TO_COMPLETED_A_JSONL> \
  <ABSOLUTE_PATH_TO_COMPLETED_B_JSONL> \
  --out <ABSOLUTE_PATH_TO_COMPARISON_JSONL>
```

This must succeed before adjudication. Verify:

- reviewer A and B identities are non-empty and distinct;
- all rows have completed annotations and correct slot lifecycle states;
- sentence-oracle ID, input, language, and locale sets match;
- neither review exposes upstream expectations or Spokenform output;
- the candidate batch has unique candidate IDs;
- every candidate maps through its source reference to one reviewed sentence
  cluster.

Stop rather than inventing missing review evidence.

## Adjudication procedure

For each sentence-oracle cluster:

1. inspect disagreement dimensions for spans, categories, semantics, ambiguity,
   policy, unit wording, accepted variants, sentence canonical output, and
   rejected variants;
2. inspect both independent rationales;
3. only now inspect candidate provenance and `source.upstream_expected`;
4. decide the final semantic interpretation and exact normalization spans;
5. decide final unit semantics, policy, canonical, accepted, and rejected forms;
6. decide the explicit full-sentence oracle;
7. record structured disagreement and source error codes;
8. assign a stable, Spokenform-owned `family_id` based on semantic/template
   family—not the importer family suggestion;
9. decide source/license disposition;
10. emit one decision for every candidate ID in the selected batch.

A batch can contain more candidate rows than sentence clusters. Promote at most
one public record for a duplicate sentence assertion unless distinct locale,
policy, provenance, or semantics justify separate records. Give every duplicate
candidate an explicit non-promoting decision such as `reject`, `keep_external`,
`quarantine`, or `needs_review`; use `source_duplicate` where applicable.

## Disposition rules

- `promote_upstream`: preserve the upstream source identity. It is permitted
  only when that source's manifest has `redistribution_status: allowed` and
  `materialization_policy: embedded_public`.
- `promote_curated`: use only for a genuinely independently authored sentence
  and oracle. Never copy upstream text and relabel it as curated.
- `keep_external`: retain a reviewed source-backed assertion outside embedded
  public Gold.
- `reject`: source duplicate, source error, out-of-scope row, or consciously
  excluded assertion.
- `quarantine`: suspicious or unresolved source material.
- `needs_review`: evidence is insufficient or semantic disagreement remains.

Your primary responsibility is to resolve A/B disagreement. A/B disagreement alone is never a reason for `needs_review`. Use it only when a named hard blocker prevents a defensible Gold decision after evaluating both reviews and allowed source/policy evidence.

For every `needs_review` or applicable `quarantine` decision, include all of:
- `blocker_code` from the registered hard-blocker set;
- `blocker_reason` explaining the concrete blocker;
- `attempted_resolution` explaining what policy/evidence was evaluated.

Run `spokenform-gold adjudication-check` before handoff. Count resolved disagreements, group unresolved rows by blocker code, flag suspicious mass deferral, and report critic challenges and validation state.
If context is genuinely ambiguous and the promotion schema cannot represent the
required canonical status safely, use `needs_review` or `quarantine`; do not
force a gold interpretation.

## Decision record contract

There must be exactly one JSONL decision per candidate ID. Even non-promoting
decisions must include `candidate_id`, `decision`, at least two reviewer IDs,
`adjudicator`, and `family_id` because the promotion CLI fails closed without
them.

A promotable decision has this shape:

```json
{
  "candidate_id": "<EXACT_CANDIDATE_ID>",
  "record_id": "<STABLE_PUBLIC_RECORD_ID>",
  "decision": "promote_upstream",
  "reviewers": ["<REVIEWER_A_ID>", "<REVIEWER_B_ID>"],
  "adjudicator": "<ADJUDICATOR_ID>",
  "family_id": "<STABLE_SPOKENFORM_FAMILY_ID>",
  "status": "gold",
  "language": "en",
  "locale": "en-US",
  "input": "Reviewed input.",
  "expected_output": "Reviewed canonical sentence.",
  "units": [],
  "negative_for": [],
  "notes": "Adjudication rationale and source-policy decision.",
  "oracle": {
    "canonical_output": "Reviewed canonical sentence.",
    "accepted_outputs": ["Reviewed canonical sentence."],
    "rejected_outputs": [],
    "variant_mode": "explicit",
    "comparison_profile": "sentence-exact-v1"
  },
  "license_disposition": "apache-2.0-upstream-embedding-approved",
  "upstream_refs": [{ "benchmark": "async_tn", "source_id": "<SOURCE_ID>" }],
  "review_protocol_version": "1.0.0",
  "disagreement": {
    "span": false,
    "category": false,
    "semantic": false,
    "ambiguity": false,
    "policy": false,
    "unit_canonical": false,
    "unit_accepted": false,
    "sentence_canonical": false,
    "sentence_accepted": false,
    "rejected_variants": false
  },
  "source_error_codes": []
}
```

Populate `units` completely for normal positive records. For `no_change`, require
`expected_output == input`, `units == []`, and non-empty `negative_for`.
`expected_output` must equal `oracle.canonical_output`, the canonical sentence
must be accepted, and accepted/rejected variants must be disjoint.

A non-promoting duplicate still needs the common identity/evidence fields:

```json
{
  "candidate_id": "<DUPLICATE_CANDIDATE_ID>",
  "decision": "reject",
  "reviewers": ["<REVIEWER_A_ID>", "<REVIEWER_B_ID>"],
  "adjudicator": "<ADJUDICATOR_ID>",
  "family_id": "<SAME_REVIEWED_FAMILY_ID>",
  "notes": "Duplicate source assertion; represented by <PUBLIC_RECORD_ID>.",
  "source_error_codes": ["source_duplicate"]
}
```

## Completeness checks

Before handoff, verify:

```text
candidate count == decision count
candidate ID set == decision candidate_id set
no duplicate candidate_id decisions
all promoted record_id values are unique and absent from canonical Gold
all reviewer pairs match the completed A/B evidence
all adjudicator fields equal <ADJUDICATOR_ID>
all promoted statuses are release eligible
all policy IDs and categories are registered
all source dispositions match sources/manifest.json
all full-sentence oracles are explicit and internally consistent
```

Do not run promotion, split, copy canonical files, or commit. Those operations
belong to the separate promotion/split/commit context.

## Handoff

Report:

```text
batch ID and artifact paths
candidate rows and sentence clusters
A/B agreement/disagreement counts
adjudicator identity
counts by decision disposition
counts by status, language, category, and source
new family IDs
source/license decisions
source error-code counts
unresolved needs_review/quarantine rows
mechanical completeness checks
```


## v2 adjudication output

Emit exactly one row per `case_id` with `decision` set to `accept`, `exclude`, or `unresolved`. An accepted row contains one complete `final_record`. Synthetic requests are candidates for a future batch and are never direct Gold. Preserve every source observation in the final record and record the adjudicator identity and rationale.
