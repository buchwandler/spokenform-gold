# Promotion, Split, Validation, and Commit — Fresh-Context Task Template

> Use only after adjudication produced one complete decision per candidate. This
> role performs mechanical promotion and integration; it does not reinterpret
> annotations. Replace every `<PLACEHOLDER>`.

---

You are the integration operator for Spokenform Gold batch **<BATCH_ID>**.

## Goal

Promote only adjudicated, license-compatible decisions into isolated staging;
run the frozen family splitter over the complete canonical corpus; validate and
inspect the generated corpus; then commit only the approved canonical data,
split-registry, policy, and documentation changes.

## Inputs

```text
repository root:   <ABSOLUTE_REPOSITORY_ROOT>
work root:         <ABSOLUTE_WORK_ROOT>
candidate batch:   <ABSOLUTE_PATH_TO_CANDIDATE_BATCH_JSONL>
decisions:         <ABSOLUTE_PATH_TO_DECISIONS_JSONL>
batch ID:          <BATCH_ID>
release version:   <CANDIDATE_VERSION>
approved extra repository paths, if any: <PATHS_OR_NONE>
```

Expected canonical inputs:

```text
data/train
data/dev
data/test
data/controls
splits/family_assignments.json
sources/manifest.json
sources/source-lock.json
```

## Read first

```text
AGENTS.md
README.md
DATA_MODEL.md
docs/ANNOTATION.md
docs/PROMOTION.md
docs/SOURCE_POLICY.md
docs/DATA_GROWTH_BATCHES.md
taxonomy/coverage_targets.json
taxonomy/release_maturity_profiles.json
sources/manifest.json
schemas/review-decision.schema.json
templates/batch-handoff.md
```

Hard boundaries:

- Gold must not be changed to match current Spokenform output.
- Do not edit adjudicated semantics during promotion.
- Do not promote missing, duplicate, or incomplete decisions.
- Do not embed a source unless its manifest permits the chosen materialization.
- Never hand-pick train/dev/test.
- Existing family assignments are immutable.
- Never copy candidate pools, review artifacts, source caches, or work reports
  into canonical data.
- Do not commit unrelated pre-existing work.

## 1. Establish a clean, attributable baseline

From the repository root:

```bash
git status --short
git diff --check
spokenform-gold validate data/train data/dev data/test
spokenform-gold gold-audit data/train data/dev data/test
spokenform-gold conflicts data/train data/dev data/test --mode unit --fail-on-conflict
spokenform-gold validate-controls data/controls
```

Record the current commit and record counts. If tracked changes already exist,
classify every changed path as either explicitly approved for this batch or
unrelated. Stop before commit if unrelated changes cannot be separated safely.
Do not reset, overwrite, or stage another person's work.

If an approved source-license policy changed, regenerate its lock before
promotion and inspect the diff:

```bash
spokenform-gold source-lock \
  --manifest sources/manifest.json \
  --out sources/source-lock.json
```

## 2. Promote into isolated staging

```bash
mkdir -p "<ABSOLUTE_WORK_ROOT>/promotion_staging"

spokenform-gold promote-reviewed \
  --candidates "<ABSOLUTE_PATH_TO_CANDIDATE_BATCH_JSONL>" \
  --decisions "<ABSOLUTE_PATH_TO_DECISIONS_JSONL>" \
  --against data/train data/dev data/test \
  --out "<ABSOLUTE_WORK_ROOT>/promotion_staging/<BATCH_ID>.jsonl" \
  --report "<ABSOLUTE_WORK_ROOT>/promotion_staging/<BATCH_ID>-report.json"
```

Promotion must fail closed if any candidate lacks exactly one decision. Inspect
the report and reconcile all counts:

```text
candidates == decisions
promoted == promote_curated + promote_upstream
all other candidates accounted for by keep_external/reject/quarantine/needs_review
promoted record IDs unique
license dispositions match adjudicated decisions
```

Do not continue if accounting differs.

## 3. Split with an isolated registry copy

Never let a failed trial mutate the canonical registry. Prepare a new output
root and copied registry:

```bash
rm -rf "<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>"
mkdir -p "<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>"
cp splits/family_assignments.json \
  "<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>/family_assignments.json"

spokenform-gold split \
  data/train data/dev data/test \
  "<ABSOLUTE_WORK_ROOT>/promotion_staging/<BATCH_ID>.jsonl" \
  --registry "<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>/family_assignments.json" \
  --out-root "<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>"
```

The generated files are:

```text
<WORK>/canonical-next/<BATCH_ID>/train/sample.jsonl
<WORK>/canonical-next/<BATCH_ID>/dev/sample.jsonl
<WORK>/canonical-next/<BATCH_ID>/test/sample.jsonl
<WORK>/canonical-next/<BATCH_ID>/family_assignments.json
```

Verify that every pre-existing family has exactly its old assignment and that
registry changes are additions only. New families may land in any deterministic
split, including train. Do not move them to make split counts look balanced.

## 4. Validate generated canonical-next before copying

```bash
NEXT="<ABSOLUTE_WORK_ROOT>/canonical-next/<BATCH_ID>"

spokenform-gold validate "$NEXT/train" "$NEXT/dev" "$NEXT/test"
spokenform-gold gold-audit "$NEXT/train" "$NEXT/dev" "$NEXT/test"
spokenform-gold conflicts \
  "$NEXT/train" "$NEXT/dev" "$NEXT/test" \
  --mode unit --fail-on-conflict \
  --out "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-conflicts-after.json"
spokenform-gold coverage \
  "$NEXT/train" "$NEXT/dev" "$NEXT/test" \
  --targets taxonomy/coverage_targets.json \
  --json "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-coverage-after.json"
spokenform-gold oracle-diff \
  data/train data/dev data/test \
  --new "$NEXT/train" "$NEXT/dev" "$NEXT/test" \
  --json "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-oracle-diff.json"
```

Inspect at minimum:

- validation and conflict results;
- promoted IDs and family assignments;
- no changed/deleted existing record IDs unless separately adjudicated;
- no changed existing oracle hashes;
- coverage gaps before versus after;
- language/category/status/source counts;
- negative-control and ambiguity impact;
- no candidate or quarantine status in canonical-next.

A large remaining coverage gap count is not a reason to fail or weaken targets.

## 5. Copy approved generated files into Git

Only after all generated checks pass:

```bash
cp "$NEXT/train/sample.jsonl" data/train/sample.jsonl
cp "$NEXT/dev/sample.jsonl" data/dev/sample.jsonl
cp "$NEXT/test/sample.jsonl" data/test/sample.jsonl
cp "$NEXT/family_assignments.json" splits/family_assignments.json
```

Do not copy any other work-root file into Git.

## 6. Run repository and release gates

```bash
spokenform-gold validate data/train data/dev data/test
spokenform-gold gold-audit data/train data/dev data/test
spokenform-gold conflicts \
  data/train data/dev data/test \
  --mode unit --fail-on-conflict \
  --out "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-conflicts-canonical.json"
spokenform-gold coverage \
  data/train data/dev data/test \
  --targets taxonomy/coverage_targets.json \
  --json "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-coverage-canonical.json"
spokenform-gold validate-controls data/controls
spokenform-gold control-coverage \
  data/controls \
  --targets taxonomy/coverage_targets.json \
  --json "<ABSOLUTE_WORK_ROOT>/reports/<BATCH_ID>-control-coverage.json"
make check

spokenform-gold release-check \
  --version "<CANDIDATE_VERSION>" \
  --data data/train data/dev data/test \
  --controls data/controls \
  --registry splits/family_assignments.json \
  --maturity candidate \
  --coverage-profile candidate \
  --out "<ABSOLUTE_WORK_ROOT>/releases/<CANDIDATE_VERSION>"
```

Do not claim stable unless `gold-audit --strict` and the stable release profile
also pass without weakening or allowed-gap shortcuts.

## 7. Inspect and commit only batch-owned changes

```bash
git status --short
git diff --check
git diff -- data/train data/dev data/test splits/family_assignments.json \
  sources/manifest.json sources/source-lock.json docs README.md
```

Confirm the diff contains only:

- generated canonical train/dev/test records;
- additive frozen family assignments;
- an explicitly approved source-policy/lock change, if applicable;
- documentation or handoff updates required by that policy/data change.

Stage explicit paths—never `git add .`:

```bash
git add \
  data/train/sample.jsonl \
  data/dev/sample.jsonl \
  data/test/sample.jsonl \
  splits/family_assignments.json \
  <APPROVED_EXTRA_PATHS_IF_ANY>

git diff --cached --check
git diff --cached --stat
git diff --cached
```

If the staged diff is correct, commit with a factual batch-specific message:

```bash
git commit -m "data: promote reviewed <BATCH_ID> records"
```

Do not amend an unrelated commit. Do not push or tag unless the user explicitly
requested publication and repository authentication is available.

## 8. Final handoff

Fill `templates/batch-handoff.md` and report:

```text
baseline commit and source revisions
candidate, decision, and disposition counts
promoted IDs and record count before/after
new family assignments and split counts
proof that existing families did not move
coverage gaps before/after
validation, conflict, audit, controls, and make-check results
candidate release path, manifest hash, and records.html path
exact committed paths and commit hash
whether push/tag/publication occurred
remaining needs_review/quarantine/license/coverage blockers
```

The task is not complete if records exist only in promotion staging or
canonical-next. It is complete only when approved generated canonical records
and their frozen split assignments are committed, all gates pass, and the
handoff distinguishes candidate maturity from stable maturity.
