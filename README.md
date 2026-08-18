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

Recommended GitHub repository:

    https://github.com/buchwandler/spokenform-gold

## Status classes

- `gold`
- `multi_valid`
- `policy_choice`
- `ambiguous`
- `quarantine`
- `no_change`

## Quick start

Requires Python 3.10+ and no runtime dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

spokenform-gold validate data/dev/sample.jsonl

spokenform-gold coverage   data/dev/sample.jsonl   --targets taxonomy/coverage_targets.json   --json reports/coverage.json

spokenform-gold conflicts data/dev/sample.jsonl --mode unit

spokenform-gold discover   examples/discovery_corpus.txt   --against data/dev/sample.jsonl   --out reports/discovery-candidates.jsonl
```

Import the async-TN evaluation JSON format:

```bash
spokenform-gold import-async /path/to/sentences.json   --out data/candidates/async-tn.jsonl
```

Imported source rows are deliberately written as `quarantine` candidates.
They must be adjudicated before being promoted into gold.

## Validate everything

```bash
make check
```

## Layout

```text
data/
  dev/
  judge_gold/
  candidates/
schemas/
taxonomy/
src/
tests/
docs/
reports/
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
