# Coding Agent: Sentence-Centric v2 Batch Preparation

> Use this role from a fresh checkout to prepare one reproducible logical data-growth batch. This role prepares observations and review artifacts. It does not perform semantic review, adjudication, promotion, splitting, or release publication.

## Primary contract

The canonical authoring source is `data/corpus.jsonl`. New sentence cases follow:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

A normal logical v2 collection batch contains up to 1,000 sentence cases. The batch size is a file and validation contract, not a requirement that one model response contain 1,000 completed JSON objects. Reviewer and adjudicator contexts may checkpoint their own work, but only complete artifacts may be handed off.

## Read first

From the repository root, read:

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

The benchmark policy defines Gold. Do not adapt Gold to upstream majority output or current Spokenform output.

## Role boundary

You may establish a baseline, verify the external source cache, ingest pinned upstreams as quarantine observations, collect the next logical batch, and prepare isolated reviewer handoffs.

You must not:

- fill reviewer A or reviewer B annotations;
- inspect another reviewer’s answers while acting as a reviewer;
- adjudicate cases;
- write accepted records into `data/corpus.jsonl`;
- assign release splits or move frozen families;
- publish a release or change Spokenform;
- manufacture reviewer identities or review evidence.

## Phase 0: establish the checkout

```bash
cd <ABSOLUTE_REPOSITORY_ROOT>
git status --short
git rev-parse HEAD
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
make check
spokenform-gold doctor
```

Record the baseline commit and classify pre-existing changes. Do not reset, stash, or overwrite another actor’s work.

## Phase 1: prepare observations

The source cache and disposable work root are external to Git. Verify configured paths and pinned revisions before ingestion:

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

Ingestion is source preparation only. Inspect row accounting, exclusions, deduplication, conflicts, coverage, and the merged observation pool. Imported rows remain quarantine observations and retain source identity, upstream expectations, hashes, and materialization policy.

## Phase 2: collect the next logical batch

Collect against the observation pool and the canonical v2 corpus:

```bash
spokenform-gold collect \
  --observations "$SPOKENFORM_GOLD_WORK/candidates/all.jsonl" \
  --reviewed data/corpus.jsonl \
  --limit 1000 \
  --batch batch-0001 \
  --out-root "$SPOKENFORM_GOLD_WORK/batches/batch-0001"
```

`collect` groups observations by `(language, locale, normalized input)` and writes:

```text
cases.jsonl
context.jsonl
a.blind.jsonl
b.blind.jsonl
batch.json
```

`batch.json` must report both selected `case_count` and complete remaining `available_case_count`. Each blind row uses `review_schema_version: "2.0.0"`, one stable `case_id`, preserved input identity, `annotation: null`, and `review.status: "unreviewed"`.

## Phase 3: independent review handoff

Hand the blind files to two distinct fresh contexts:

```text
$SPOKENFORM_GOLD_WORK/batches/batch-0001/a.blind.jsonl -> reviewer A
$SPOKENFORM_GOLD_WORK/batches/batch-0001/b.blind.jsonl -> reviewer B
```

Use `templates/reviewer-ab-task.md`. Reviewer A and reviewer B must use truthful stable identities and must not inspect source expectations, `context.jsonl`, current Spokenform output, or each other’s work.

For a large batch, a reviewer may write to `a.complete.partial.jsonl` or `b.complete.partial.jsonl` while working. A checkpoint must keep the same reviewer identity and preserved case fields. It is not a valid handoff. When all cases are complete, atomically produce `a.complete.jsonl` or `b.complete.jsonl` and run full-file validation.

## Phase 4: review-check

Only the adjudicator may continue after both independent reviews are complete:

```bash
spokenform-gold review-check \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001" \
  --review-a "$SPOKENFORM_GOLD_WORK/batches/batch-0001/a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/batches/batch-0001/b.complete.jsonl" \
  --json "$SPOKENFORM_GOLD_WORK/batches/batch-0001/review-check.json"
```

Require `ready=true`, exact case-ID coverage, correct slots, distinct reviewer identities, complete annotations, and no forbidden source or implementation output. Stop on failure. Do not search for substitute artifacts.

## Phase 5: adjudication

Use `templates/adjudicator-task.md` in a separate context. The adjudicator may inspect source observations only after `review-check` is ready and writes exactly one `accept`, `exclude`, or `unresolved` decision per `case_id` to `adjudicated.jsonl`.

For a large logical batch, `adjudicated.partial.jsonl` may be used as a same-adjudicator checkpoint. It must never be handed to integration. The final `adjudicated.jsonl` must contain exactly one decision for every case ID, and unresolved cases cannot enter Gold.

## Phase 6: integrate, validate, and report

Run a dry run before writing canonical data:

```bash
spokenform-gold integrate \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001"

spokenform-gold integrate \
  --batch "$SPOKENFORM_GOLD_WORK/batches/batch-0001" \
  --write

spokenform-gold validate data/corpus.jsonl
spokenform-gold report \
  --records data/corpus.jsonl \
  --out "$SPOKENFORM_GOLD_WORK/reports/corpus.html"
```

Integration must preserve source observations and v2 identity, omit `split`, omit persisted `sentence_oracle_id`, and reject unresolved or incomplete decisions. Humans inspect generated HTML reports rather than editing or enumerating JSONL rows.

## Stop conditions

Stop and report a blocker when source revisions or required paths are missing, row accounting fails, candidate validation fails, review independence is not genuine, a complete artifact is unavailable, source materialization is not permitted, or an existing canonical identity or family would need to change.

Never lower coverage targets, majority-vote source outputs, translate missing language coverage without independent review, or copy restricted upstream datasets into Git.

## Compatibility-only workflows

The repository still supports legacy candidate ranking, `review-batch`, `blind-review`, `promote-reviewed`, family splitting, and canonical rereview for compatibility consumers. Those commands are not the v2 authoring path and must not replace `collect` or write new data directly into `data/corpus.jsonl`.
