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
  test/
  dev/
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
