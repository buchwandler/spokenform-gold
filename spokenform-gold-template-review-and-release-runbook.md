# Spokenform Gold Review and Release Runbook

This runbook is the operational companion to the task templates in
`templates/`. It separates semantic review from mechanical integration and
release work. The benchmark policy and schemas are authoritative; current
Spokenform output and upstream expected strings are evidence, not Gold
authority.

## Workflow

```text
baseline and path resolution
        |
        +--> canonical re-review:
        |       blank A/B -> independent A/B reviews
        |       -> preflight -> comparison -> canonical adjudication
        |       -> isolated oracle application -> validation/audit
        |
        +--> new data:
                quarantine ingestion -> coverage/ranking
                -> bounded independent A/B review
                -> candidate adjudication -> promotion staging
                -> frozen family split -> candidate release
                                                        |
                                                        v
                                         Spokenform integration
                                                        |
                                                        v
                                              stable release gates
                                                        |
                                                        v
                                           explicit publication
```

Use separate contexts for independent reviewers, adjudication, mechanical
integration, and publication. Do not invent reviewer identities or silently
repair incomplete evidence.

## Authoritative inputs

Before a non-trivial run, read:

- `AGENTS.md`
- `README.md`
- `DATA_MODEL.md`
- `docs/ANNOTATION.md`
- `docs/ORACLE_REVIEW.md`
- `docs/SOURCE_POLICY.md`
- `taxonomy/categories.json`
- `taxonomy/coverage_targets.json`
- the schemas named by the applicable task template

Resolve configured paths first:

```bash
spokenform-gold doctor
```

The external source cache and work root are disposable build state. Review
artifacts, candidate pools, reports, and release outputs must not be copied into
Git unless an explicit policy requires a small audit artifact.

## Canonical re-review

Canonical records do not store `sentence_oracle_id`. The supported review API
derives it from language, locale, and normalized input. Do not recreate it in an
ad-hoc script.

### Prepare independent review artifacts

```bash
spokenform-gold prepare-canonical-rereview \
  --records data/train data/dev data/test \
  --review-id canonical-rereview-<DATE> \
  --out-root "$SPOKENFORM_GOLD_WORK/reviews/canonical"
```

This creates:

```text
canonical-a.blind.jsonl
canonical-b.blind.jsonl
manifest.json
```

Complete A and B in genuinely isolated contexts using
`templates/reviewer-ab-task.md`. Each reviewer must not see the other review,
upstream expected output, current Spokenform output, comparisons, or decisions.
Validate each completed artifact independently:

```bash
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" --slot A
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" --slot B
```

### Mandatory aggregate gate

Run this before inspecting source evidence, Git history, release reports,
canonical oracle values, or current implementation output:

```bash
spokenform-gold review-preflight \
  --records data/train data/dev data/test \
  --review-a "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --json "$SPOKENFORM_GOLD_WORK/reviews/canonical/preflight.json"
```

If `ready=no`, stop immediately. Do not search for alternative review files,
run comparison or adjudication, fabricate identities, or repair mismatched
review evidence.

### Compare and adjudicate

Only after `ready=yes`:

```bash
spokenform-gold compare-reviews \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --out "$SPOKENFORM_GOLD_WORK/reviews/canonical/comparison.jsonl"
```

Use `templates/canonical-rereview-adjudicator-task.md` to produce one decision
for every derived `sentence_oracle_id`, using
`schemas/canonical-review-decision.schema.json`. Preserve the existing record
ID, family ID, source identity, input, language, and locale. Do not make source
materialization or promotion decisions in this role.

Each decision must contain complete units and a full-sentence `oracle` with:

- `canonical_output`;
- explicit `accepted_outputs`;
- explicit `rejected_outputs`;
- `variant_mode: "explicit"`.

Verify that the decision count and identity set exactly match the canonical
records. Record SHA256 hashes for both completed reviews, the comparison, and
the decisions. Hand these artifacts to the separate mechanical integration
context.

## Canonical mechanical integration

Use `templates/canonical-rereview-integration-task.md` only after preflight,
comparison, and adjudication are complete. It may run:

```bash
spokenform-gold apply-reviewed-oracles \
  --records data/train data/dev data/test \
  --review-a "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --decisions "$SPOKENFORM_GOLD_WORK/reviews/canonical/decisions.jsonl" \
  --out-root "$SPOKENFORM_GOLD_WORK/reviews/canonical/integration"
```

Keep output isolated. Inspect the oracle diff and verify that record IDs, family
IDs, source provenance, frozen family assignments, and split membership are
unchanged except for the intended oracle/review metadata. Restore deterministic
`train`, `dev`, and `test` shards with the frozen family splitter; never
hand-pick a split.

Before any copy into Git, run:

```bash
spokenform-gold validate data/train data/dev data/test
spokenform-gold gold-audit data/train data/dev data/test
spokenform-gold conflicts data/train data/dev data/test --mode unit
spokenform-gold coverage \
  data/train data/dev data/test \
  --targets taxonomy/coverage_targets.json \
  --json "$SPOKENFORM_GOLD_WORK/reports/coverage-after.json"
spokenform-gold validate-controls data/controls
spokenform-gold control-coverage \
  data/controls \
  --targets taxonomy/coverage_targets.json \
  --json "$SPOKENFORM_GOLD_WORK/reports/control-coverage.json"
```

Copy only after explicit approval. The integration role does not reinterpret
semantics, edit decisions, change taxonomy or policy, or update Spokenform
pins.

## New candidate data

Keep upstream datasets logically separate and preserve their provenance. Import
into quarantine candidates; never promote imported rows automatically.

For a production refresh, pin and verify source revisions first:

```bash
spokenform-gold source-lock \
  --manifest sources/manifest.json \
  --out sources/source-lock.json
spokenform-gold ingest-upstreams \
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt \
  --reviewed data/train data/dev data/test \
  --targets taxonomy/coverage_targets.json \
  --batch-limit 100
```

Inspect row accounting, deduplication, conflicts, exclusions, coverage, and
ranked candidates before selecting a bounded review batch. Use independent A/B
review contexts and `templates/adjudicator-task.md`. Candidate adjudication
must decide status, family, oracle, and license/materialization disposition.

Promote only reviewed decisions:

```bash
spokenform-gold promote-reviewed \
  --candidates "$SPOKENFORM_GOLD_WORK/review_batches/batch-0001.jsonl" \
  --decisions "$SPOKENFORM_GOLD_WORK/reviews/batch-0001-decisions.jsonl" \
  --against data/train data/dev data/test \
  --out "$SPOKENFORM_GOLD_WORK/promotion_staging/batch-0001.jsonl" \
  --report "$SPOKENFORM_GOLD_WORK/promotion_staging/batch-0001-report.json"
```

Run the frozen family splitter over the complete canonical corpus plus the
staging records. Inspect the family-registry diff before copying generated
shards into Git. Regenerate ranking and coverage after each bounded batch.

## Release ladder

A candidate release is for integration testing and may still expose coverage or
review gaps:

```bash
spokenform-gold release-check \
  --version 0.x.y-candidate.N \
  --data data/train data/dev data/test \
  --controls data/controls \
  --maturity candidate \
  --out "$SPOKENFORM_GOLD_WORK/releases/0.x.y-candidate.N"
```

A stable release requires strict audit and stable coverage gates:

```bash
spokenform-gold gold-audit data/train data/dev data/test --strict
spokenform-gold release-check \
  --version X.Y.Z \
  --data data/train data/dev data/test \
  --controls data/controls \
  --maturity stable \
  --coverage-profile stable \
  --out "$SPOKENFORM_GOLD_WORK/releases/X.Y.Z"
```

Do not weaken coverage, oracle, control, provenance, or review gates to make a
release pass. Spokenform must consume an immutable accepted release, not the
external candidate work directory.

## Handoff checklist

Every review, integration, or release handoff records:

- source revisions and row-accounting summary;
- candidate, exclusion, and disposition counts;
- coverage gaps before and after the change;
- review and adjudication artifact paths;
- reviewer and adjudicator identities;
- changed family assignments, if any;
- oracle, comparison, decision, split, and release hashes;
- validation, audit, conflict, control, and coverage results;
- approval, copy, commit, publication, and downstream-pin state;
- unresolved semantic, source, license, or policy blockers.

Never claim completion from proposals, quarantine candidates, or work-root
artifacts alone.

## Stop conditions

Stop and report a blocker when:

- pinned source revisions or row accounting fail;
- review artifacts are incomplete, blank, mismatched, or not independent;
- canonical identity, family assignment, or source identity would change;
- semantic context is insufficient and ambiguity would be hidden;
- source materialization is not permitted;
- a frozen family would move across splits;
- validation, strict audit, controls, conflicts, coverage, or release checks fail.

## Human review interface and correction flow

JSONL remains the machine interchange format. It is not the human review interface.
After A/B review, compare and adjudicate automatically, run the deterministic quality gate, and generate:

```bash
spokenform-gold adjudication-check --candidates ... --review-a ... --review-b ... --comparison ... --decisions ...
spokenform-gold review-report --candidates ... --review-a ... --review-b ... --comparison ... --decisions ... --out review-report.html
```

The human handoff must say **Open `review-report.html`**, and must report candidate/cluster counts, A/B agreement/disagreement, resolved dispositions, hard blockers, critic challenges, and validation state. Do not ask the human to inspect `comparison.jsonl`, edit JSONL, find line numbers, or maintain a disagreement list.

Canonical release records use immutable `record.id` as the correction handle:

```bash
spokenform-gold trace-record <record-id>
spokenform-gold prepare-correction <record-id>
spokenform-gold apply-correction <record-id> --correction decision.json
```

These commands resolve review lineage, source references, hashes, correction history, and previews from the record ID. Normal corrections preserve record ID, family, and source identity; an input correction may change the derived `sentence_oracle_id` while historical evidence remains archived.
