# Spokenform Gold

A policy-driven text-normalization benchmark layer for Spokenform.

`spokenform-gold` does **not** replace PolyNorm, async-TN, or Proteno. Those
benchmarks remain immutable upstream suites. This repository provides a
canonical layer that can:

- preserve source provenance;
- import upstream examples as candidates, not unquestioned gold;
- distinguish canonical wording from semantically acceptable variants;
- mark ambiguous or broken examples instead of forcing a single answer;
- validate benchmark records mechanically;
- detect contradictions between sources;
- report category / language / ambiguity / negative-control coverage;
- discover unseen token shapes in real text;
- maintain a separate human-labelled judge-validation set.

## Sentence-level oracle

Canonical records use an explicit full-sentence oracle:

```json
"oracle": {
  "canonical_output": "Use a three quarters inch bolt.",
  "accepted_outputs": [
    "Use a three quarters inch bolt.",
    "Use a three fourths inch bolt."
  ],
  "rejected_outputs": [],
  "variant_mode": "explicit",
  "comparison_profile": "sentence-exact-v1"
}
```

`expected_output` remains a compatibility alias and must equal `oracle.canonical_output` for reviewed records. Accepted scoring uses the explicit full-sentence list; it does not silently accept every Cartesian product of unit variants. `oracle_hash` covers the semantic assertion and excludes volatile notes and review metadata.

Use `spokenform-gold gold-audit ... --strict` for stable-oracle checks, `spokenform-gold oracle-diff OLD --new NEW` for deterministic answer changes, `spokenform-gold migrate-oracle` for legacy seed migration, and `spokenform-gold blind-review` to create first-pass artifacts that hide upstream expected outputs.

## Status classes

- `gold`
- `multi_valid`
- `policy_choice`
- `ambiguous`
- `quarantine`
- `no_change`

## Quick start

Requires Python 3.10+ and no runtime dependencies. Install the optional dev
tooling when you want the benchmark checks, lint, and report regeneration
commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

spokenform-gold validate data/dev/sample.jsonl
spokenform-gold validate data/test/sample.jsonl
spokenform-gold validate data/judge_gold/sample.jsonl --judge

spokenform-gold stats      data/candidates/*.jsonl   --json reports/candidate_stats.json
spokenform-gold coverage   data/dev/*.jsonl   data/test/*.jsonl   --targets taxonomy/coverage_targets.json   --json reports/coverage.json
spokenform-gold split      data/dev/sample.jsonl   data/test/sample.jsonl   --registry splits/family_assignments.json   --seed 20260818   --out-root /tmp/spokenform-gold-split-check
spokenform-gold release-check   --version 0.2.0-exp   --data data/dev data/test   --registry splits/family_assignments.json   --maturity experimental   --out /tmp/spokenform-gold-release
spokenform-gold judge-calibrate   data/judge_gold/*.jsonl   --predictions tests/fixtures/predictions/judge_predictions.jsonl   --json reports/judge_calibration.json

spokenform-gold conflicts data/dev/sample.jsonl --mode unit

spokenform-gold discover   examples/discovery_corpus.txt   --against data/dev/sample.jsonl   --out reports/discovery-candidates.jsonl
```

Import the pinned upstream source-bundle fixtures:

```bash
spokenform-gold import-async /path/to/sentences.json   --suite english   --out data/candidates/async-tn.jsonl
spokenform-gold import-polynorm /path/to/polynorm_bench   --format official   --out data/candidates/polynorm.jsonl
spokenform-gold import-proteno /path/to/proteno/data/English   --format official   --out data/candidates/proteno-en.jsonl
```

Imported source rows are deliberately written as `quarantine` candidates.
They must be adjudicated before being promoted into gold.

## Release-pipeline commands

```bash
spokenform-gold split data/dev/*.jsonl data/test/*.jsonl --registry splits/family_assignments.json --seed 20260818 --out-root /tmp/spokenform-gold-split-check
spokenform-gold score data/test/*.jsonl --predictions tests/fixtures/predictions/sample_predictions.jsonl --mode canonical --json reports/score.json
spokenform-gold adjudicate-queue data/candidates/*.jsonl --conflicts reports/conflicts.json --coverage reports/coverage.json --out reports/adjudication.jsonl
spokenform-gold judge-calibrate data/judge_gold/*.jsonl --predictions tests/fixtures/predictions/judge_predictions.jsonl --json reports/judge_calibration.json
spokenform-gold release-check --version 0.2.0-exp --data data/dev data/test --registry splits/family_assignments.json --maturity experimental --out dist/spokenform-gold-v0.2.0-exp
```

Release maturity rules are machine-readable in
`taxonomy/release_maturity_profiles.json`. `experimental`, `candidate`, and
`stable` releases use the same release builder with progressively stricter
coverage, category, language, and negative-control gates.

Public release builds validate only the sources actually referenced by the
reviewed release data. Source manifests also carry a
`materialization_policy`, so `metadata_only` / restricted third-party sources
cannot be embedded accidentally; keep those sources local and use
source-backed overlays when a benchmark needs external hydration.

## Fixed profiles and control suites

Canonical scoring uses the frozen `gold-v1` profile from
`taxonomy/evaluation_profiles.json`. The registry records the complete runtime
configuration, inheritance, policy-expansion status, and deterministic hashes.
Benchmark and release artifacts include the selected profile and registry
identity. Unknown profiles fail closed, and control rows cannot provide
arbitrary runtime keyword arguments.

Configuration-sensitive behavior is evaluated separately from canonical Gold.
Control records live under `data/controls/`, reference one or more fixed profile
IDs, and may assert expected output plus stable ownership rules such as
`protected`, `semantic.quantities`, or `fallback.sequence`:

```bash
spokenform-gold validate-controls data/controls/*.jsonl
spokenform-gold control-coverage data/controls/*.jsonl \
  --targets taxonomy/coverage_targets.json \
  --json reports/control_coverage.json
spokenform-gold score-controls data/controls/*.jsonl \
  --predictions predictions/control.jsonl \
  --json reports/control_score.json
```

Control metrics are not merged into canonical accuracy. Policy-expanding
profiles, such as sequence fallback spelling and literal promotion, remain
labelled separately. Control records are curated benchmark assertions, not a
mechanism for searching configurations to maximize score.

## External runner contract

`spokenform-gold` owns benchmark policy, JSONL data, and scoring. External
benchmark runners should emit prediction records shaped as:

```json
{ "id": "record-id", "output": "Predicted spoken form" }
```

Then call the Gold scorer or benchmark runner via the CLI or package API:

```python
from spokenform_gold import score_records
from spokenform_gold.benchmark import run_benchmark
```

This repository also ships a repository-local benchmark runner that exercises
the Gold release contract with an explicit profile and a pluggable prepare
wrapper:

```bash
python -m benchmarks.spokenform_gold \
  --gold-root /tmp/spokenform-gold-release \
  --split test \
  --results-dir /tmp/spokenform-gold-results \
  --prepare-module tests.fixtures.runner.sample_prepare:prepare_gold_record
```

The runner verifies release hashes, loads records by split and optional
filters, writes `summary.json`, `predictions.jsonl`, `failures.jsonl`, and
`failures.md`, and records the applied profile in the summary artifact.

If a release contains source-backed `external_ref` records, pass a
`source_loader` callable through the Python API so the runner can hydrate the
upstream text from a local source bundle before scoring.

## Validate everything

```bash
make check
```

## Layout

```text
data/
  train/
  dev/
  test/
  judge_gold/
  candidates/
splits/
schemas/
taxonomy/
benchmarks/
tests/
docs/
reports/
sources/
```

## Split and candidate policy

The canonical benchmark uses a family-safe 70/15/15 `train`/`dev`/`test` split. Existing family assignments are frozen in `splits/family_assignments.json`; adding a new family assigns it deterministically without moving earlier families. The initial `data/train/sample.jsonl` shard may be empty because the original reviewed families were already assigned to `dev` or `test`. Future promoted families must be split before they enter canonical data.

Candidate-only regression proposals, including `data/candidates/01_todo_regressions.jsonl`, are not Gold. They require independent review, adjudication, a Spokenform-owned family ID, and an explicit source or license decision before promotion. Pinned upstream caches and raw review artifacts remain outside Git. Czech is a coverage target but requires independently reviewed data; it must not be filled by unreviewed translation.


## Growth loop

```text
upstream benchmark / real corpus / regression failure
                    |
                    v
                 candidate
                    |
                    v
           conflict + coverage analysis
                    |
                    v
             independent review
                    |
                    v
               adjudication
                    |
                    v
             Spokenform Gold
```

For each production bug fix, add a family rather than only one regression row:
a positive example, boundary variants, an ambiguity case where relevant, and
negative controls where false positives are plausible.

## Experimental release scope

The checked-in corpus is now a reproducible experimental release seed with:

- pinned source metadata and local cache hashes in `sources/manifest.json`;
- a frozen family assignment registry in `splits/family_assignments.json`;
- reviewed English, German, and Spanish high-risk benchmark examples plus
  broader candidate-maturity coverage for score/range, math, cardinal,
  ordinal, measurement, and URL/email families;
- candidate import fixtures for async-TN, PolyNorm, and Proteno;
- official-format PolyNorm and Proteno importer fixtures plus source-backed
  overlay plumbing for restricted upstream corpora;
- a local release loader and benchmark runner for deterministic score artifacts;
- judge calibration metrics for precision/recall and false acceptance/rejection
  analysis.

It is still intentionally **experimental**: coverage targets remain far above
the current reviewed corpus, and release success is not a claim of full
benchmark completeness.

## Publishing

Create an empty repository named `spokenform-gold` under `buchwandler`, then:

```bash
git init
git add .
git commit -m "Initial Spokenform Gold MVP"
git branch -M main
git remote add origin git@github.com:buchwandler/spokenform-gold.git
git push -u origin main
```

Do not add full upstream datasets until redistribution terms and attribution
requirements have been checked.

## Scaled upstream candidate ingestion

The importers consume local source bundles and never require network access at runtime. Keep source bundles outside the repository:

```text
$SPOKENFORM_GOLD_SOURCE_CACHE/
  async_tn/
  polynorm/
  proteno/

$SPOKENFORM_GOLD_WORK/
  candidates/
  exclusions/
  reports/
```

Current Async JSON artifacts are supported directly:

```bash
spokenform-gold import-async "$SPOKENFORM_GOLD_SOURCE_CACHE/async_tn/data/sentences.json" \
  --suite english --out "$SPOKENFORM_GOLD_WORK/candidates/async_en.jsonl" \
  --exclusions-out "$SPOKENFORM_GOLD_WORK/exclusions/async_en.json" \
  --report-out "$SPOKENFORM_GOLD_WORK/reports/async_en.json"

spokenform-gold import-async "$SPOKENFORM_GOLD_SOURCE_CACHE/async_tn/data/multilingual-sentences.json" \
  --suite multilingual --out "$SPOKENFORM_GOLD_WORK/candidates/async_multilingual.jsonl" \
  --exclusions-out "$SPOKENFORM_GOLD_WORK/exclusions/async_multilingual.json" \
  --report-out "$SPOKENFORM_GOLD_WORK/reports/async_multilingual.json"
```

All imported rows remain `quarantine`. Review candidates after running:

```bash
spokenform-gold dedupe-candidates "$SPOKENFORM_GOLD_WORK/candidates/*.jsonl" --out "$SPOKENFORM_GOLD_WORK/reports/dedupe.json"
spokenform-gold family-suggestions "$SPOKENFORM_GOLD_WORK/candidates/*.jsonl" --out "$SPOKENFORM_GOLD_WORK/reports/families.json"
spokenform-gold source-lock --manifest sources/manifest.json --out sources/source-lock.json
```

Duplicate reports preserve every source identity and distinguish exact input overlap from conflicting upstream output. Family suggestions are review inputs only. They do not assign release split families or promote candidates.

The complete deterministic workflow is available through one command. It expects source checkouts at the pinned revisions from `sources/manifest.json`; fetching remains an explicit external operation:

```bash
spokenform-gold ingest-upstreams \
  --source-cache "$SPOKENFORM_GOLD_SOURCE_CACHE" \
  --work-root "$SPOKENFORM_GOLD_WORK" \
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt
```

The command imports Async English and multilingual JSON, the recursive PolyNorm official tree, and Proteno English and Spanish paired-list directories. It verifies Git revisions when checkout metadata is available, validates every generated candidate file, fails on row-accounting errors, and writes merge, dedupe, family, conflict, reviewed-coverage, ranking, exclusion, pool-summary, and review-batch artifacts under the work root.

The individual analysis commands are also available:

```bash
spokenform-gold merge-candidates "$SPOKENFORM_GOLD_WORK/candidates/async_*.jsonl" --out "$SPOKENFORM_GOLD_WORK/candidates/all.jsonl"
spokenform-gold analyze-exclusions "$SPOKENFORM_GOLD_WORK"/exclusions/*.json --out "$SPOKENFORM_GOLD_WORK/reports/exclusions.json"
spokenform-gold rank-candidates "$SPOKENFORM_GOLD_WORK/candidates/async_*.jsonl" --against data/dev data/test --targets taxonomy/coverage_targets.json --out "$SPOKENFORM_GOLD_WORK/reports/ranked_candidates.jsonl"
spokenform-gold review-batch "$SPOKENFORM_GOLD_WORK/reports/ranked_candidates.jsonl" --limit 100 --max-per-category 20 --max-per-family-suggestion 5 --out "$SPOKENFORM_GOLD_WORK/review_batches/batch-0001.jsonl"
```

These artifacts are candidate workflow outputs, not Gold. Imported records remain `status=quarantine`, retain `source.upstream_expected` and source hashes, and must be independently reviewed before promotion. Do not commit full restricted source bundles or change source `release_ready` flags during ingestion.

The repository keeps only fixture-derived candidate examples in Git. The checked-in fixture pool now contains eight Async candidates (English plus six multilingual rows) and six PolyNorm candidates (raw plus official projections, including the explicit metadata-only unsupported-category row). This expansion is provenance-preserving and all rows remain `status=quarantine`. Full pinned upstream bundles must remain in the external source cache.

For a complete refresh, inspect per-shard row accounting before review:

```bash
spokenform-gold pool-stats "$SPOKENFORM_GOLD_WORK/candidates/*.jsonl" \
  --exclusions "$SPOKENFORM_GOLD_WORK"/exclusions/*.json \
  --reports "$SPOKENFORM_GOLD_WORK"/reports/imports/*.json \
  --conflicts "$SPOKENFORM_GOLD_WORK/reports/dedupe.json" \
  --out "$SPOKENFORM_GOLD_WORK/reports/upstream_pool_summary.json"
```

## Data-growth execution status

The deterministic ingestion workflow has been exercised against a local fixture cache using the pinned Async, PolyNorm, and Proteno source layouts. The run produced five row-accounted shards, 17 merged quarantine candidates, one explicit PolyNorm `unsupported_category` exclusion, zero conflicts, and a 17-record review batch. The candidate pool covered six languages (`de`, `en`, `es`, `fr`, `it`, `pt`); Czech remains a curated coverage target rather than an upstream ingestion language.

The reviewed corpus remains 62 records with 15 observed categories and 390 reported coverage gaps. These gaps are intentionally visible. Stable maturity now rejects remaining coverage gaps unless an explicit allowed-gap policy is configured, so satisfying the language minimum alone cannot make an incomplete corpus stable.

The fixture run is triage evidence only. Candidates retain quarantine status, source provenance, upstream expectations, and source hashes. Independent semantic review, Spokenform-owned family assignment, license/materialization decisions, and promotion remain outstanding. Full pinned upstream checkouts must still be supplied externally for a production refresh.

## Data-growth batch contract

Full-dataset growth is executed in bounded batches. The checked-in repository
contains canonical `data/train`, `data/dev`, and `data/test` release inputs;
`data/train` is part of release materialization, while the normal Spokenform
benchmark defaults to the held-out `test` split. Selecting `all` is explicit and
must not silently change the default benchmark split.

Batch 0 is repository/process hygiene. Batch 1 targets stable-required category
and surface coverage using only reviewed policy and available candidate evidence.
Batch 2 expands multilingual coverage and reports Czech gaps until independently
authored and reviewed Czech records exist. Upstream and discovered rows remain
quarantine candidates until two independent reviews, adjudication, a
Spokenform-owned family, and a source/materialization decision are recorded.

Review artifacts and upstream caches belong in the disposable external work root.
They are not release data and must not be copied into `data/train`, `data/dev`, or
`data/test` merely because a ranker, model, or current Spokenform output suggests
an answer.


## Strict re-review workflow

Existing canonical records can be re-reviewed without mutating Git-tracked Gold.
Generate independent blind artifacts into the external work root:

```bash
python -m spokenform_gold.cli blind-review   data/train data/dev data/test   --reviewer-slot A   --out ../spokenform-gold-work/reviews/existing-a.jsonl

python -m spokenform_gold.cli blind-review   data/train data/dev data/test   --reviewer-slot B   --out ../spokenform-gold-work/reviews/existing-b.jsonl
```

After both genuine reviewers complete their annotations, compare them:

```bash
python -m spokenform_gold.cli compare-reviews   ../spokenform-gold-work/reviews/existing-a-completed.jsonl   ../spokenform-gold-work/reviews/existing-b-completed.jsonl   --out ../spokenform-gold-work/reviews/existing-comparison.jsonl
```

Apply adjudicated decisions only to a new output root:

```bash
python -m spokenform_gold.cli apply-reviewed-oracles   --records data/train data/dev data/test   --review-a ../spokenform-gold-work/reviews/existing-a-completed.jsonl   --review-b ../spokenform-gold-work/reviews/existing-b-completed.jsonl   --decisions ../spokenform-gold-work/reviews/existing-decisions.jsonl   --out-root ../spokenform-gold-work/canonical-reviewed
```

The workflow requires a deterministic sentence-oracle identity, matching
input/language/locale, two distinct reviewer IDs, an adjudicator, and decisions
that preserve the canonical record ID, family ID, source provenance, and review
disagreement. It recomputes oracle_hash, validates every resulting record, and
writes records.jsonl, comparisons.jsonl, and report.json only beneath a new
isolated output root. It never invents reviewer evidence or promotes a row
because current Spokenform output happens to match.
