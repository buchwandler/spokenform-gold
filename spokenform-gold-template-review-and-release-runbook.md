# Spokenform Gold Review and Release Runbook

This runbook describes the primary sentence-centric v2 workflow for producing reviewed Gold data. Compatibility workflows remain available in the final sections, but they are not the authoring path for new sentence cases.

## Primary contract

The canonical authoring source is `data/corpus.jsonl`. It has no `split`, no persisted `sentence_oracle_id`, and no duplicate legacy `expected_output` state. New data follows:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

A normal logical production batch contains up to 1,000 sentence cases. The 1,000 cases are one file and validation contract. Reviewers and adjudicators may checkpoint their own files, but the final artifacts must contain the complete case-ID set and partial files must never be handed off.

The benchmark policy defines Gold. Upstream expected strings and current Spokenform output are evidence only.

## Read before operating

```text
AGENTS.md
README.md
DATA_MODEL.md
docs/ANNOTATION.md
docs/SOURCE_POLICY.md
taxonomy/categories.json
taxonomy/coverage_targets.json
sources/manifest.json
templates/reviewer-ab-task.md
templates/adjudicator-task.md
```

Resolve configured paths before source work:

```bash
spokenform-gold doctor
```

Keep source caches and review artifacts in the configured external work root. Do not copy restricted source bundles into Git.

## Stage 1: prepare the observation pool

Verify the pinned source cache and create source-lock evidence:

```bash
python scripts/setup-source-cache.py --verify-only
spokenform-gold source-lock \
  --manifest sources/manifest.json \
  --out sources/source-lock.json

spokenform-gold ingest-upstreams \
  --source-cache "$SPOKENFORM_GOLD_SOURCE_CACHE" \
  --work-root "$SPOKENFORM_GOLD_WORK" \
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt
```

Inspect at least:

```text
reports/ingestion-summary.json
reports/upstream_pool_summary.json
reports/dedupe.json
reports/conflicts.json
reports/coverage-reviewed.json
reports/exclusions.json
census/summary.json
candidates/all.jsonl
```

Require pinned revisions, required paths, row accounting, candidate validation, source identity, upstream expectations, and materialization metadata to be intact. Ingestion creates quarantine observations. It does not adjudicate, assign Gold families, or promote data.

## Stage 2: collect one v2 logical batch

```bash
spokenform-gold collect \
  --observations "$SPOKENFORM_GOLD_WORK/candidates/all.jsonl" \
  --reviewed data/corpus.jsonl \
  --limit 1000 \
  --batch batch-0001 \
  --out-root "$SPOKENFORM_GOLD_WORK/batches/batch-0001"
```

Collection groups observations by `(language, locale, normalized input)` and writes:

```text
cases.jsonl
context.jsonl
a.blind.jsonl
b.blind.jsonl
batch.json
```

Check that `batch.json` records the selected `case_count` and complete remaining `available_case_count`. Every blind row must use `review_schema_version: "2.0.0"`, a stable `case_id`, preserved input identity, `annotation: null`, and `review.status: "unreviewed"`.

## Stage 3: independent A/B review

Use `templates/reviewer-ab-task.md` in two genuinely independent fresh contexts:

```text
$SPOKENFORM_GOLD_WORK/batches/batch-0001/a.blind.jsonl -> reviewer A
$SPOKENFORM_GOLD_WORK/batches/batch-0001/b.blind.jsonl -> reviewer B
```

The reviewers must not see `context.jsonl`, source expectations, current Spokenform output, the other review, comparisons, or decisions. Each reviewer preserves the blind identity fields and writes only their own final artifact:

```text
$SPOKENFORM_GOLD_WORK/batches/batch-0001/a.complete.jsonl
$SPOKENFORM_GOLD_WORK/batches/batch-0001/b.complete.jsonl
```

For a large batch, `a.complete.partial.jsonl` and `b.complete.partial.jsonl` are permitted checkpoints. They must retain one truthful reviewer identity and are never complete handoff artifacts. The final complete files must cover the exact full case-ID set once and pass `validate-review --contract v2`; the authoritative pre-adjudication gate is Stage 4 `review-check`.

## Stage 4: aggregate review-check gate

Before source inspection or adjudication, run:

```bash
spokenform-gold review-check \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001" \
  --review-a "$SPOKENFORM_GOLD_WORK/batches/batch-0001/a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/batches/batch-0001/b.complete.jsonl" \
  --json "$SPOKENFORM_GOLD_WORK/batches/batch-0001/review-check.json"
```

Require `ready=true`, exact case-ID coverage, correct reviewer slots, distinct stable reviewer IDs, complete annotations, and no forbidden source or implementation output. If the gate is not ready, stop. Do not search for alternative files or fabricate missing evidence.

## Stage 5: adjudicate

Use `templates/adjudicator-task.md` only after review-check is ready. The adjudicator may inspect both reviews, source observations, and upstream expectations. The adjudicator writes exactly one `accept`, `exclude`, or `unresolved` row per case ID to:

```text
$SPOKENFORM_GOLD_WORK/batches/batch-0001/adjudicated.jsonl
```

Accepted rows contain complete v2 `final_record` objects. Unresolved cases remain outside Gold. A/B disagreement alone is not a blocker; unresolved requires a named hard blocker, reason, and attempted resolution.

For a 1,000-case logical file, `adjudicated.partial.jsonl` is allowed as a same-adjudicator checkpoint only. The final `adjudicated.jsonl` must contain one decision per case ID with no duplicates and must never be replaced by a partial file.

## Stage 6: integrate and inspect

Run a dry run first:

```bash
spokenform-gold integrate \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001"
```

After decisions are complete and the dry run is clean:

```bash
spokenform-gold integrate \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001" \
  --write

spokenform-gold validate data/corpus.jsonl
spokenform-gold report \
  --records data/corpus.jsonl \
  --out "$SPOKENFORM_GOLD_WORK/reports/corpus.html"
```

Integration preserves source observations and canonical identity, rejects unresolved or incomplete decisions, and does not add `split` or persisted `sentence_oracle_id`. Humans receive `review-report.html` or `records.html`; do not ask humans to inspect, edit, or enumerate JSONL rows. Corrections use the permanent `record.id`.

## Release checks

After a reviewed increment, inspect validation, coverage, conflicts, and controls. Candidate and stable release commands remain separate from authoring:

```bash
spokenform-gold validate data/corpus.jsonl
spokenform-gold report --records data/corpus.jsonl --out "$SPOKENFORM_GOLD_WORK/reports/corpus.html"
```

Do not claim stable completeness from a candidate artifact. Stable gates must retain strict oracle, provenance, coverage, control, and review requirements.

## Human review interface

JSONL is machine interchange, not the human UI. Batch review produces `review-report.html`, and release inspection produces `records.html`. Human corrections identify the permanent `record.id`. A/B disagreement is resolved by adjudication; it is not silently dropped. `needs_review` and applicable `quarantine` decisions require a named hard blocker, blocker reason, and attempted resolution.

## Compatibility-only canonical rereview

Existing canonical records can still use the compatibility canonical rereview workflow. It is not a method for creating new v2 sentence cases. Its artifacts remain explicitly named:

```text
canonical-a.blind.jsonl
canonical-a.complete.jsonl
canonical-b.blind.jsonl
canonical-b.complete.jsonl
preflight.json
comparison.jsonl
decisions.jsonl
manifest.json
schemas/canonical-review-decision.schema.json
```

Run `review-preflight` before source inspection. Canonical records do not store `sentence_oracle_id`; the identity is derived by the supported review API. Apply corrections only through the dedicated compatibility integration task, preserving record, family, source, and split identity.

## Compatibility-only pre-v2 candidate and split workflow

The former candidate ranking and split-based promotion commands remain available for compatibility consumers. They are not the v2 authoring path:

```bash
spokenform-gold review-batch ...
spokenform-gold blind-review ...
spokenform-gold promote-reviewed ...
spokenform-gold split ...
```

Legacy candidate rows remain quarantine material until independent review, adjudication, source-policy, family, and release gates pass. Never use these commands as a substitute for `collect`, and never silently copy their output into `data/corpus.jsonl`.
