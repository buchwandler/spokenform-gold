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

## Quick start (MVP smoke examples; dev/test-only)

These small commands exercise the seed corpus. They are not the production
release contract; production validation and release construction always use
`data/train`, `data/dev`, and `data/test`.

Requires Python 3.10+; Python 3.10 installs the small TOML compatibility
dependency automatically. Install the optional dev
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

## Production validation and release path

Use all canonical shards for production validation, coverage, promotion, and
release construction:

```bash
spokenform-gold validate data/train data/dev data/test
spokenform-gold gold-audit data/train data/dev data/test
spokenform-gold coverage data/train data/dev data/test --targets taxonomy/coverage_targets.json --json reports/coverage-production.json
spokenform-gold release-check --version 0.2.0-candidate.1 --data data/train data/dev data/test --controls data/controls --registry splits/family_assignments.json --maturity candidate --coverage-profile candidate --out ../spokenform-gold-work/releases/0.2.0-candidate.1
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
spokenform-gold split data/train/*.jsonl data/dev/*.jsonl data/test/*.jsonl --registry splits/family_assignments.json --seed 20260818 --out-root /tmp/spokenform-gold-split-check
spokenform-gold score data/test/*.jsonl --predictions tests/fixtures/predictions/sample_predictions.jsonl --mode canonical --json reports/score.json
spokenform-gold adjudicate-queue data/candidates/*.jsonl --conflicts reports/conflicts.json --coverage reports/coverage.json --out reports/adjudication.jsonl
spokenform-gold judge-calibrate data/judge_gold/*.jsonl --predictions tests/fixtures/predictions/judge_predictions.jsonl --json reports/judge_calibration.json
spokenform-gold release-check --version 0.2.0-exp --data data/train data/dev data/test --controls data/controls --registry splits/family_assignments.json --maturity experimental --coverage-profile experimental --out dist/spokenform-gold-v0.2.0-exp
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

The checked-in corpus currently passes the **candidate** release gate, not the
stable gate. Publish it as a GitHub prerelease by pushing a version tag:

```bash
git tag -a v0.1.0-candidate.1 -m "Spokenform Gold 0.1.0 candidate 1"
git push origin v0.1.0-candidate.1
```

`.github/workflows/release.yml` reruns all checks, builds the immutable release,
and publishes `.tar.gz` and `.zip` downloads plus archive checksums. Every
archive includes `records.html`, a self-contained, searchable browser for the
release records, coverage, provenance, and review metadata. Open it directly in
a browser after extracting the archive; it has no network dependencies.

A release can also be started manually from the GitHub Actions **publish
benchmark release** workflow by entering a version and maturity. Non-stable
maturities are marked as GitHub prereleases. Stable publication remains blocked
until the strict review, seven-language, controls, and zero-gap gates pass.

Do not add full upstream datasets until redistribution terms and attribution
requirements have been checked.

## Runtime path configuration

The repository-root `config.toml` is the normal local configuration for the
external source cache and disposable work root:

```toml
[paths]
source_cache = "../spokenform-gold-source-cache"
work = "../spokenform-gold-work"
```

After `python scripts/setup-source-cache.py`, run the orchestrator from the
repository root without path flags:

```bash
spokenform-gold ingest-upstreams \
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt \
  --reviewed data/train data/dev data/test \
  --targets taxonomy/coverage_targets.json \
  --batch-limit 100
```

Path precedence is `CLI > environment > config.toml`. Use
`SPOKENFORM_GOLD_SOURCE_CACHE` and `SPOKENFORM_GOLD_WORK`, or the explicit
`--source-cache` and `--work-root` flags, as overrides for custom locations.
The cache and work directories remain external runtime state and are not
created by configuration loading.

## Compatibility-only: scaled upstream candidate ingestion

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
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt
```

The command imports Async English and multilingual JSON, the recursive PolyNorm official tree, and Proteno English and Spanish paired-list directories. It verifies Git revisions when checkout metadata is available, validates every generated candidate file, fails on row-accounting errors, and writes merge, dedupe, family, conflict, reviewed-coverage, ranking, exclusion, pool-summary, and review-batch artifacts under the work root.

The individual analysis commands are also available:

```bash
spokenform-gold merge-candidates "$SPOKENFORM_GOLD_WORK/candidates/async_*.jsonl" --out "$SPOKENFORM_GOLD_WORK/candidates/all.jsonl"
spokenform-gold analyze-exclusions "$SPOKENFORM_GOLD_WORK"/exclusions/*.json --out "$SPOKENFORM_GOLD_WORK/reports/exclusions.json"
spokenform-gold rank-candidates "$SPOKENFORM_GOLD_WORK/candidates/async_*.jsonl" --against data/train data/dev data/test --targets taxonomy/coverage_targets.json --out "$SPOKENFORM_GOLD_WORK/reports/ranked_candidates.jsonl"
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

## Primary data-growth workflow: sentence-centric v2

New authoring data lives in `data/corpus.jsonl`, which has no `split` field. The primary path is:

```text
collect -> review-check -> adjudicate -> integrate -> validate -> report
```

Run collection against the external candidate pool and canonical corpus:

```bash
spokenform-gold collect \
  --observations "$SPOKENFORM_GOLD_WORK/candidates/all.jsonl" \
  --reviewed data/corpus.jsonl \
  --limit 1000 \
  --batch batch-0003 \
  --out-root "$SPOKENFORM_GOLD_WORK/batches/batch-0003"
```

`collect` groups observations by `(language, locale, normalized input)` and emits `cases.jsonl`, `context.jsonl`, `a.blind.jsonl`, and `b.blind.jsonl`. Each blind reviewer row uses the v2 `case_id` contract and starts with `annotation: null` and `review.status: "unreviewed"`. Reviewers work in distinct fresh contexts and write `.complete.jsonl` artifacts without source expectations or current Spokenform output.


For an individual completed v2 artifact, use `spokenform-gold validate-review <PATH> --slot A|B --contract v2` as a mechanical check. It does not replace the mandatory A/B `review-check` gate before adjudication.
The default logical `collect` batch is 1,000 sentence cases. Reviewers and adjudicators may checkpoint file production under one stable identity, but `review-check` and integration accept only complete artifacts covering the full case-ID set. Partial files are never handoff inputs.

After both completed reviews pass `spokenform-gold review-check`, a separate adjudicator writes exactly one `accept`, `exclude`, or `unresolved` row per `case_id` to `adjudicated.jsonl`. Accepted rows contain complete v2 `final_record` objects. Synthetic requests remain candidates for a future independent batch, and unresolved cases cannot enter Gold.

The integration context runs a dry run before `integrate --write`, then `spokenform-gold validate` and `spokenform-gold report`. Humans inspect generated HTML reports, not JSONL rows. The benchmark policy defines Gold; upstream outputs and current Spokenform output are evidence only.

## Compatibility-only split workflow

The former ranking, promotion, family split, and split-based release commands remain available for compatibility and release consumers. They are not the authoring path for new sentence cases. Review artifacts and upstream caches remain in the disposable external work root and must not be copied into canonical data without independent review, adjudication, and source-policy decisions.

## Strict canonical re-review workflow

Existing canonical records can be re-reviewed without mutating Git-tracked Gold. Canonical records do not store `sentence_oracle_id`; the review identity is deterministically derived from language, locale, and normalized input by the supported review API.

Resolve configured external paths first:

```bash
spokenform-gold doctor
```

Prepare visibly distinct blank artifacts and a manifest under `$SPOKENFORM_GOLD_WORK/reviews/canonical/`:

```bash
spokenform-gold prepare-canonical-rereview \
  --records data/train data/dev data/test \
  --review-id canonical-rereview-<DATE> \
  --out-root "$SPOKENFORM_GOLD_WORK/reviews/canonical"
```

This creates only `canonical-a.blind.jsonl`, `canonical-b.blind.jsonl`, and `manifest.json`. Each reviewer writes a new `.complete.jsonl` artifact and checks it independently with the compatibility-only canonical contract:

```bash
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  --slot A --contract canonical
spokenform-gold validate-review \
  "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --slot B --contract canonical
```

Run the aggregate first gate before source inspection or comparison:

```bash
spokenform-gold review-preflight \
  --records data/train data/dev data/test \
  --review-a "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-a.complete.jsonl" \
  --review-b "$SPOKENFORM_GOLD_WORK/reviews/canonical/canonical-b.complete.jsonl" \
  --json "$SPOKENFORM_GOLD_WORK/reviews/canonical/preflight.json"
```

If `ready=no`, stop: do not inspect source evidence, Git history, release/audit artifacts, current Spokenform output, or alternative review files. Do not fabricate reviewer IDs or write comparison/decision artifacts. Only when ready run `compare-reviews`, adjudicate under policy, and hand off to `templates/canonical-rereview-integration-task.md` for mechanical application.

Canonical decisions use `schemas/canonical-review-decision.schema.json`, not the candidate promotion schema. The integration context alone may run `apply-reviewed-oracles` into an isolated work-root output; it must preserve record/family/source identity and frozen splits before explicit approval to copy any canonical shard.

## Human review interface

JSONL remains the machine interchange format. Batch review produces a human-facing `review-report.html`; release inspection uses `records.html`. Do not ask humans to inspect comparison JSONL, edit rows, find line numbers, or maintain disagreement lists.

A/B disagreement is resolved by the adjudicator and deterministic quality gate. `needs_review` and `quarantine` require a named hard blocker, reason, and attempted resolution. Canonical correction requests use the permanent `record.id`:

```bash
spokenform-gold trace-record <record-id>
spokenform-gold prepare-correction <record-id>
spokenform-gold apply-correction <record-id> --correction decision.json
```

Normal corrections preserve `record.id`, family, and source identity. Review lineage and correction history are retained in sanitized `review-evidence.jsonl`.


## Sentence-centric v2 authoring workflow

New authoring data lives in `data/corpus.jsonl`. Canonical records do not contain `split`; `family_id` remains available for consumer-side leakage-safe export. Source observations are grouped before review, and one sentence case receives one A/B review pair and one adjudication.

The normal workflow is:

```text
collect → review-check → adjudicate → integrate → validate → report
```

Use the primary commands:

```bash
spokenform-gold doctor
spokenform-gold collect --limit 1000 --batch batch-0001 --out-root ../spokenform-gold-work/batches/batch-0001
spokenform-gold review-check --batch ../spokenform-gold-work/batches/batch-0001 --review-a ../spokenform-gold-work/batches/batch-0001/a.complete.jsonl --review-b ../spokenform-gold-work/batches/batch-0001/b.complete.jsonl
spokenform-gold integrate --batch ../spokenform-gold-work/batches/batch-0001 --write
spokenform-gold validate
spokenform-gold report --out ../spokenform-gold-work/reports/records.html
```

The adjudicator may emit synthetic candidates, but a new sentence remains outside Gold until it receives independent A/B review. Restricted upstream observations retain external references and are not silently embedded. Immutable v1 split releases remain loadable, while v2 releases are built with `spokenform-gold release --version VERSION --out PATH` and contain `corpus.jsonl`.
