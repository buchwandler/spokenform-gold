# Sentence Oracle Review Artifacts

Canonical re-review artifacts live in the external configured work root, not in
`data/train`, `data/dev`, or `data/test`.

## Three contracts

1. **Blind row** — `canonical-a.blind.jsonl` or `canonical-b.blind.jsonl`; it has
   context and source references but `annotation: null`, `review.status:
   unreviewed`, and no reviewer identity.
2. **Completed reviewer row** — the corresponding `.complete.jsonl`; one isolated
   reviewer adds one stable `reviewer_id`, a complete annotation, and the slot
   lifecycle state. Validate it independently with `validate-review`.
3. **Canonical decision** — an adjudicator artifact using
   `schemas/canonical-review-decision.schema.json`; it records two reviewer IDs,
   an adjudicator, final oracle data, disagreement, and source-error metadata.

Canonical records do **not** store `sentence_oracle_id`. Review identity is
provided by the supported `sentence_oracle_id(record)` API and is derived from
language, locale, and normalized input. Never inspect a nonexistent canonical
field or reproduce the hash in an ad-hoc script.

## Artifact lifecycle and names

Use these names for new canonical reviews:

```text
reviews/canonical/
  canonical-a.blind.jsonl
  canonical-a.complete.jsonl
  canonical-b.blind.jsonl
  canonical-b.complete.jsonl
  preflight.json
  comparison.jsonl
  decisions.jsonl
  manifest.json
```

The old `existing-a.jsonl` / `existing-b.jsonl` names are legacy preparation
names only and must not be reused for new runs.

## Fresh-context workflow

Resolve configured paths without filesystem hunting:

```bash
spokenform-gold doctor
```

Create independent blind artifacts, complete them in separate contexts, and
validate each completed artifact:

```bash
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" --slot A
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" --slot B
```

Run the aggregate readiness gate before reading source evidence, Git history,
release reports, current Spokenform output, or canonical oracle values:

```bash
spokenform-gold review-preflight \
  --records data/train data/dev data/test \
  --review-a "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --json "$SPOKENFORM_GOLD_WORK/reviews/canonical/preflight.json"
```

If `ready=no`, stop immediately. Do not inspect semantic source evidence, search
for alternative reviews, run adjudication/audit/release commands, or write a
comparison or decision artifact. Missing reviewer IDs, incomplete annotations,
shared reviewers, slot/lifecycle errors, ID-set mismatches, context mismatches,
and canonical identity mismatches remain blockers.

Only after `ready=yes` may an adjudicator run:

```bash
spokenform-gold compare-reviews \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --out "$SPOKENFORM_GOLD_WORK/reviews/canonical/comparison.jsonl"
```

`apply-reviewed-oracles` belongs to the separate mechanical integration role in
`templates/canonical-rereview-integration-task.md`. It requires one decision per
derived canonical identity, preserves record/family/source identity, recomputes
`oracle_hash`, validates output, and writes only to an isolated output root.
