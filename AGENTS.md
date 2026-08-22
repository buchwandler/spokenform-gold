# AGENTS.md

## Purpose

This repository is **Spokenform Gold**, the canonical benchmark, annotation,
validation, coverage, and oracle-governance layer for the Spokenform text
normalization project.

The repository is intended to answer four separate questions:

1. **Correctness** — did Spokenform produce the preferred normalization?
2. **Semantics** — did the output preserve the intended meaning?
3. **Robustness** — did Spokenform avoid changing text that should remain unchanged?
4. **Coverage** — does the benchmark actually test the important normalization space?

Do not collapse these questions into a single metric or a single expected string.

---

## Read this first

Before making non-trivial changes, read:

1. `README.md`
2. `DATA_MODEL.md`
3. `docs/ANNOTATION.md`
4. `docs/SOURCE_POLICY.md`
5. `docs/ROADMAP.md`
6. `taxonomy/categories.json`
7. `taxonomy/coverage_targets.json`

If the repository also contains the long-form development reference, use it as
the architectural source of truth.

---

## Core rule

**The benchmark policy defines gold. The current Spokenform implementation does not.**

Never change a gold annotation merely because Spokenform currently emits a
different output.

Correct direction:

```text
normalization policy
        ↓
semantic annotation
        ↓
gold record
        ↓
Spokenform implementation
```

Forbidden direction:

```text
Spokenform implementation
        ↓
rewrite benchmark expectation
```

---

# Repository role

`spokenform-gold` does **not** replace:

- PolyNorm
- async-TN
- Proteno

Those are upstream benchmark sources with their own assumptions and policies.

This repository must:

- preserve upstream provenance;
- import upstream rows as candidates;
- identify contradictions;
- adjudicate differences explicitly;
- represent ambiguity explicitly;
- maintain Spokenform-specific canonical policy;
- track missing coverage;
- maintain negative controls;
- validate semantic judges independently.

Do not silently rewrite upstream benchmark data.

---

# Status model

Canonical records use these statuses:

- `gold`
- `multi_valid`
- `policy_choice`
- `ambiguous`
- `quarantine`
- `no_change`

Use them deliberately.

## `gold`

Use when the semantic interpretation is clear and the preferred Spokenform
realization has been reviewed.

## `multi_valid`

Use when multiple spoken realizations are semantically and policy-equivalent.

Example:

```text
3/4
```

may accept:

```text
three quarters
three fourths
```

while retaining one canonical realization.

## `policy_choice`

Use when more than one interpretation or convention is plausible, but a
Spokenform locale/profile explicitly chooses one.

## `ambiguous`

Use when the input does not contain enough information to determine one
semantic interpretation.

Do not force ambiguous examples into `gold`.

## `quarantine`

Use when imported or existing source annotation is suspicious, incomplete,
broken, inconsistent, or not yet reviewed.

Imported upstream data should default to `quarantine` or another unreviewed
candidate state. It must not automatically become trusted gold.

## `no_change`

Use for negative controls.

For `no_change` records:

```text
expected_output == input
units == []
negative_for != []
```

Negative controls are first-class benchmark data.

---

# Data model invariants

The canonical interchange format is JSONL.

A normal benchmark record must preserve:

```text
id
language
locale
split
family_id
status
input
expected_output
source
units
negative_for
notes
```

Each normalization unit should preserve:

```text
surface
start
end
category
semantic
policy
canonical
accepted
rejected
features
```

Do not remove fields merely because the current implementation does not use
them yet.

---

# Provenance is mandatory

Every record must have source provenance.

At minimum:

```json
{
  "benchmark": "spokenform_curated",
  "source_id": "..."
}
```

For imported data, preserve as much of the following as available:

```text
benchmark
source_id
source_version
source_category
source_url
commit
license
license_note
upstream_expected
importer_version
source_hash
```

Never overwrite `upstream_expected` with the Spokenform Gold canonical output.

If source and Spokenform policy disagree, store both.

---

# Import policy

Importers must be loss-minimizing.

They should:

1. parse the upstream format;
2. preserve original input;
3. preserve upstream expected normalization;
4. preserve source IDs;
5. preserve source categories;
6. preserve source language/locale;
7. retain source-specific metadata;
8. map into the Spokenform schema without hiding lossy mappings;
9. emit candidate/quarantine records;
10. never silently promote imported data into gold.

Current MVP command:

```bash
spokenform-gold import-async SOURCE.json \
  --out data/candidates/async-tn.jsonl
```

Future importers should follow the same principles:

```bash
spokenform-gold import-polynorm ...
spokenform-gold import-proteno ...
```

---

# Source datasets

Keep upstream datasets logically separate.

Recommended source identities:

```text
async_tn
polynorm
proteno
spokenform_curated
spokenform_regression
spokenform_discovered
```

Do not combine records in a way that destroys source identity.

Do not redistribute full third-party datasets until their license and
redistribution requirements have been reviewed.

---

# Semantic representation

Prefer machine-readable semantics over string-only truth.

Examples:

## Decimal

```json
{
  "value": "0.02"
}
```

Do not use binary floating-point when exact written decimal semantics matter.

## Date

```json
{
  "year": 2025,
  "month": 3,
  "day": 4
}
```

## Fraction

```json
{
  "numerator": 3,
  "denominator": 4
}
```

## Currency

```json
{
  "currency": "USD",
  "major": 1234,
  "minor": 50
}
```

## IP address

```json
{
  "address": "192.168.0.1"
}
```

Semantic meaning should be validated separately from surface wording wherever
practical.

---

# Canonical versus acceptable output

Do not treat every acceptable spoken variant as a new canonical form.

Maintain this distinction:

```text
canonical
accepted
rejected
```

Example:

```text
surface:
    3/4

canonical:
    three quarters

accepted:
    three quarters
    three fourths

rejected:
    three slash four
```

The long-term benchmark should expose both:

```text
canonical score
semantic acceptance score
```

Do not make canonical scoring fuzzy by default.

---

# Ambiguity is part of the benchmark

Important ambiguity families include forms such as:

```text
3/4
1.2
1.2.3
192.168.0.1
404
3-2
10:30
AB12
ART
IDs
.3
1st
```

When adding support for an ambiguous surface, add contrastive contexts.

Example:

```text
The score was 3-2.
Calculate 3-2.
I initiate in 3-2-1.
The range is 3-2.
```

The benchmark should test context-sensitive interpretation, not merely pattern
recognition.

---

# Family IDs and split leakage

`family_id` is mandatory because near-duplicate templates must not leak across
evaluation splits.

Wrong:

```text
May 12 → dev
May 13 → test
May 14 → challenge
```

if all three came from the same template family.

Split by family, not by row.

A `family_id` must not cross frozen train/dev/test/challenge boundaries.

Do not bypass the validator to permit family leakage.

---

# Regression policy

A confirmed Spokenform bug should create a **regression family**, not only one
test sentence.

Prefer:

```text
1 canonical positive
2 boundary variants
1 ambiguity case, when applicable
2 negative controls, when false positives are plausible
```

Examples already represented in the MVP include:

```text
.3
.02
IDs
ART
3-2-1
192.168.0.1
v2.0.0-beta.4
03/04/2025
3/4
```

When fixing a production failure, ask:

```text
What broader family does this failure belong to?
What nearby false positive could this fix introduce?
What input would distinguish the intended interpretation from a competing one?
```

---

# Negative controls

Do not optimize only for inputs that require normalization.

Examples of useful negative controls:

```text
May I come in?
The art department opened today.
Point three is the critical argument.
March was unusually warm.
Version control is useful.
```

For each new positive rule, actively consider nearby text that should remain
unchanged.

False-positive normalization is a benchmark failure.

---

# Coverage requirements

Category count alone is insufficient.

Coverage should eventually track:

```text
language
locale
category
surface_pattern
semantic_role
length
leading_zero
sign
decimal_separator
group_separator
case_pattern
separator
sentence_position
punctuation_context
single_vs_multiple_units
ambiguity_family
unicode_variant
source
status
```

Use:

```text
taxonomy/coverage_targets.json
```

to define required coverage.

The coverage command must report gaps rather than hiding low-frequency
categories.

Current MVP:

```bash
spokenform-gold coverage \
  data/dev/sample.jsonl \
  --targets taxonomy/coverage_targets.json \
  --json reports/coverage.json
```

A large number of coverage gaps in the MVP is expected and desirable. It means
the tooling is exposing missing data.

Do not weaken coverage targets merely to make the report look better.

---

# Discovering missing data

New benchmark candidates should come from several sources:

1. upstream benchmark conflicts;
2. Spokenform regressions;
3. real-world corpora;
4. low-coverage feature families;
5. language gaps;
6. ambiguity gaps;
7. negative-control gaps;
8. disagreement between independent systems.

Current discovery command:

```bash
spokenform-gold discover corpus.txt \
  --against data/dev/sample.jsonl \
  --out data/candidates/discovered.jsonl
```

Discovery output is a candidate pool, not gold.

---

# Conflict handling

Use:

```bash
spokenform-gold conflicts data/candidates/*.jsonl
```

Do not resolve conflicts automatically by majority vote.

A conflict can represent:

```text
equivalent realizations
policy difference
locale difference
semantic difference
source error
insufficient context
real ambiguity
```

The correct action may be:

```text
merge accepted variants
create locale-specific policy
mark ambiguous
quarantine source
adjudicate canonical
```

Never assume the largest source is correct.

---

# Annotation workflow

For material intended to become stable gold, prefer independent review.

Annotators should independently answer:

1. What span requires normalization?
2. What category is it?
3. What does it mean?
4. Is it ambiguous?
5. What is the preferred canonical spoken form?
6. Which alternatives preserve meaning?
7. Which plausible alternatives are actually wrong?

Do not show annotator B annotator A's answer before independent annotation.

Track disagreement separately for:

```text
span
category
semantic interpretation
canonical realization
accepted variants
```

High disagreement may mean the correct status is `ambiguous`.

---

# Mechanical validation

Always run validation after changing benchmark data.

```bash
spokenform-gold validate data/dev/sample.jsonl
```

Validation should enforce or evolve toward enforcing:

```text
schema validity
duplicate IDs
category validity
source provenance
surface existence
start/end alignment
duplicate-surface disambiguation
unit overlap rules
canonical in accepted
accepted/rejected disjointness
status invariants
family leakage
semantic validity
```

Do not weaken validation just to accept broken source data.

Use `quarantine` instead.

---

# Category semantics

Add category-specific semantic validators over time.

Recommended package:

```text
src/spokenform_gold/semantics/
```

Suggested validators:

```text
date
time
decimal
currency
fraction
ip_address
version
identifier
measurement_unit
```

Examples that should eventually fail validation:

```text
2025-02-30
192.168.300.1
fraction denominator = 0
```

---

# Judge policy

A hosted or local LLM may assist with semantic acceptance, but it is not the
gold authority.

Use models for:

```text
candidate generation
conflict explanation
equivalence suggestions
triage
semantic-judge proposals
```

Do not use a model as an unquestioned final annotator.

The judge itself must be benchmarked against:

```text
data/judge_gold/
```

Current MVP:

```bash
spokenform-gold validate data/judge_gold/sample.jsonl --judge
```

---

# Judge evaluation

A future judge evaluation must track more than aggregate accuracy.

Required metrics should include:

```text
false acceptance rate
false rejection rate
precision
recall
per-category accuracy
per-language accuracy
ambiguity-family accuracy
```

False acceptance is especially dangerous:

```text
candidate changes semantic meaning
judge incorrectly accepts candidate
```

---

# Scoring design

Implement deterministic scoring before model-based judging.

Recommended order:

1. canonical exact/tightly-normalized scoring;
2. explicit accepted-variant scoring;
3. semantic-object validation;
4. optional semantic judge.

Future command:

```bash
spokenform-gold score \
  data/test/en-US.jsonl \
  --predictions predictions.jsonl \
  --mode canonical
```

Report at minimum:

```text
sentence accuracy
unit accuracy
category accuracy
language accuracy
status breakdown
no_change accuracy
false-positive normalization rate
```

Do not report only one global percentage.

---

# Taxonomy policy

Canonical categories are defined in:

```text
taxonomy/categories.json
```

Treat taxonomy names as versioned API.

Do not casually rename, merge, or split categories.

Breaking taxonomy changes require explicit versioning and migration.

Source-specific category mappings should eventually live under:

```text
taxonomy/mappings/
```

and should preserve whether mappings are:

```text
exact
broader
narrower
ambiguous
unsupported
```

Do not hide lossy mappings.

---

# Policy registry

Policies referenced by units should eventually be registered in:

```text
taxonomy/policies.json
```

Examples:

```text
natural-decimal
en-US-mdY
spell-initialism-preserve-plural
ipv4-digitwise
semantic-version
countdown-no-range-word
```

Do not create many near-duplicate unnamed policies in data rows.

---

# Preferred coding style

Core tooling should remain:

- Python 3.10+
- deterministic;
- network-independent;
- small and modular;
- type-annotated where useful;
- easy to inspect;
- easy to test;
- standard-library-first.

Prefer pure functions for:

```text
validation
coverage
conflict detection
semantic checking
scoring
```

Avoid introducing a database until scale actually requires one.

JSONL remains the canonical source format for early versions.

---

# Dependency policy

Keep core runtime dependencies minimal.

Optional functionality should use optional dependency groups.

Possible future groups:

```text
dev
judge-openai
judge-gemini
dashboard
parquet
```

Core validation and scoring must not require a hosted service.

---

# Determinism

Generated reports and transformed data should have stable ordering where
practical.

Prefer sorting by:

```text
record ID
category
language
locale
source
family ID
```

Avoid random output ordering.

If randomness is required, expose and record the seed.

---

# Testing

Run tests before completing a code or data change.

Current MVP:

```bash
python -m unittest discover -s tests -v
```

or:

```bash
make check
```

Tests should cover:

```text
schema errors
duplicate IDs
span mismatch
repeated spans
accepted/rejected overlap
status invariants
family leakage
category validation
coverage counting
conflict detection
discovery shapes
importers
scoring
splitting
semantic validators
```

Importers must use local fixtures and must not require network access.

---

# CI expectations

Target CI should eventually check:

```text
Python 3.10
Python 3.11
Python 3.12
Python 3.13
```

Minimum checks:

```bash
python -m unittest
spokenform-gold validate data/dev/*.jsonl
spokenform-gold validate data/test/*.jsonl
spokenform-gold validate data/judge_gold/*.jsonl --judge
spokenform-gold coverage ...
```

Do not merge benchmark-changing code that bypasses failing validation.

---

# Data changes in pull requests

A benchmark-changing PR should explain:

```text
what changed
why it changed
source/provenance
coverage impact
score impact
status changes
policy impact
annotation evidence
```

A policy change must be explicitly identified as a policy change.

Do not disguise policy changes as annotation fixes.

---

# Suggested benchmark PR checklist

- [ ] New records validate.
- [ ] No duplicate IDs.
- [ ] No family leakage.
- [ ] Source provenance is present.
- [ ] Upstream expected output is preserved where relevant.
- [ ] Coverage impact was reviewed.
- [ ] Ambiguity is explicit.
- [ ] New regression family includes nearby negatives where appropriate.
- [ ] Accepted and rejected variants do not overlap.
- [ ] Documentation was updated.
- [ ] Tests pass.

---

# Release/versioning policy

Benchmark releases are versioned independently of Spokenform releases.

Example:

```text
spokenform-gold v0.1.0
spokenform-gold v0.2.0
spokenform-gold v1.0.0
```

A released benchmark version should be immutable.

Release metadata should eventually include:

```text
dataset files
taxonomy version
policy version
source manifests
coverage report
judge calibration report
checksums
release notes
```

Never report a benchmark result without identifying the benchmark version.

---

# Source licensing

Distinguish:

```text
repository code
locally curated gold data
third-party source data
```

They may have different license requirements.

Do not add full third-party corpora to this repository until redistribution and
attribution requirements are known.

Importer code and source metadata are safer than blindly vendoring upstream
datasets.

---

# Current MVP commands

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Validate:

```bash
spokenform-gold validate data/dev/sample.jsonl
```

Validate judge gold:

```bash
spokenform-gold validate data/judge_gold/sample.jsonl --judge
```

Coverage:

```bash
spokenform-gold coverage \
  data/dev/sample.jsonl \
  --targets taxonomy/coverage_targets.json \
  --json reports/coverage.json
```

Conflict detection:

```bash
spokenform-gold conflicts data/dev/sample.jsonl --mode unit
```

Discovery:

```bash
spokenform-gold discover \
  examples/discovery_corpus.txt \
  --against data/dev/sample.jsonl \
  --out reports/discovery-candidates.jsonl
```

Import async-TN:

```bash
spokenform-gold import-async /path/to/sentences.json \
  --out data/candidates/async-tn.jsonl
```

Full MVP check:

```bash
make check
```

---

# Current priority: produce the reviewed Gold corpus

The repository infrastructure is already substantially implemented: source
manifests and locks, Async/PolyNorm/Proteno importers, candidate merge and
deduplication, coverage analysis, family-aware splitting, sentence-oracle
validation, promotion, control suites, scoring, release construction, and the
Spokenform benchmark adapter all exist.

Do **not** spend the next data-growth cycle rebuilding those mechanisms unless a
concrete production run exposes a defect. The primary task is now to turn the
full pinned upstream candidate pool plus curated regressions into reviewed,
Git-tracked Gold records.

A useful mental model is:

```text
external source cache
        ↓
deterministic quarantine candidate pool
        ↓
coverage/conflict/dedup ranking
        ↓
blind review A + blind review B
        ↓
adjudication + source-policy decision
        ↓
promotion staging
        ↓
frozen family split
        ↓
Git-tracked train/dev/test Gold
        ↓
candidate release
        ↓
stable release after strict review + coverage gates
        ↓
Spokenform pins immutable Gold release
```

## What "full Gold dataset" means

A full Gold dataset is **not** a copy of PolyNorm, Proteno, or Async TN and is
not a merged file of upstream expected outputs.

It is the reviewed canonical corpus under `data/train`, `data/dev`, and
`data/test`, where every release record:

- has a stable ID and Spokenform-owned `family_id`;
- has explicit language, locale, status, units, policy, source provenance, and
  full-sentence oracle;
- keeps accepted outputs explicit and rejected variants separate;
- records ambiguity instead of guessing;
- has a source/materialization decision compatible with redistribution;
- belongs to exactly one frozen family split;
- passes validation, conflict, oracle, coverage, and release checks.

The external work directory is disposable build state. The Git-tracked reviewed
records and immutable release artifact are the benchmark.

## Production data-growth loop

For a production refresh, keep upstream repositories outside Git:

```bash
export SPOKENFORM_GOLD_SOURCE_CACHE=/path/to/spokenform-gold-source-cache
export SPOKENFORM_GOLD_WORK=/path/to/spokenform-gold-work
```

Populate the cache at the exact revisions from `sources/manifest.json`, then run:

```bash
spokenform-gold source-lock \
  --manifest sources/manifest.json \
  --out sources/source-lock.json

spokenform-gold ingest-upstreams \
  --source-cache "$SPOKENFORM_GOLD_SOURCE_CACHE" \
  --work-root "$SPOKENFORM_GOLD_WORK" \
  --sources async_tn polynorm proteno \
  --languages en de es fr it pt \
  --reviewed data/train data/dev data/test \
  --targets taxonomy/coverage_targets.json \
  --batch-limit 100
```

Before annotation, inspect at minimum:

```text
reports/ingestion-summary.json
reports/upstream_pool_summary.json
reports/dedupe.json
reports/conflicts.json
reports/coverage-reviewed.json
reports/ranked_candidates.jsonl
reports/exclusions.json
census/summary.json
review_batches/batch-0001.jsonl
```

Reject the run if row accounting fails, pinned source revisions are wrong,
candidate validation fails, or source/output conflicts are silently collapsed.

## Review batches

Work in bounded batches. Prefer 50–100 records, then regenerate ranking after
each promotion so the next batch follows the remaining coverage gaps.

Create blind reviewer artifacts from the selected review batch:

```bash
spokenform-gold blind-review \
  "$SPOKENFORM_GOLD_WORK/review_batches/batch-0001.jsonl" \
  --reviewer-slot A \
  --out "$SPOKENFORM_GOLD_WORK/reviews/batch-0001-a.jsonl"

spokenform-gold blind-review \
  "$SPOKENFORM_GOLD_WORK/review_batches/batch-0001.jsonl" \
  --reviewer-slot B \
  --out "$SPOKENFORM_GOLD_WORK/reviews/batch-0001-b.jsonl"
```

Reviewer A and reviewer B must not see `source.upstream_expected`, each other's
annotation, or Spokenform's current output before committing their independent
semantic judgment.

Automation or an LLM may prepare proposals, find spans, detect disagreements,
and suggest variants. Proposal generation does not make a row Gold. For a
stable release, preserve genuinely independent review evidence and an
adjudicator rather than inventing reviewer identities.

## Adjudication and decision files

For each candidate, produce exactly one review decision compatible with
`schemas/review-decision.schema.json`.

Promotion decisions must include at least:

```text
candidate_id
decision
reviewers (2+ independent IDs)
adjudicator
family_id
status
input
expected_output
units
negative_for
notes
oracle
license_disposition
```

Use `promote_curated` by default when the sentence/oracle is independently
authored and upstream material is only lineage evidence. Use
`promote_upstream` only when the source manifest explicitly permits embedding
the upstream material. Otherwise use `keep_external`, `reject`, `quarantine`,
or `needs_review`.

Never change Gold to match current Spokenform output.

## Promotion, split, and canonical merge

Promote one completed batch to staging:

```bash
spokenform-gold promote-reviewed \
  --candidates "$SPOKENFORM_GOLD_WORK/review_batches/batch-0001.jsonl" \
  --decisions "$SPOKENFORM_GOLD_WORK/reviews/batch-0001-decisions.jsonl" \
  --against data/train data/dev data/test \
  --out "$SPOKENFORM_GOLD_WORK/promotion_staging/batch-0001.jsonl" \
  --report "$SPOKENFORM_GOLD_WORK/promotion_staging/batch-0001-report.json"
```

Do not hand-pick a split. Run the frozen family splitter over the complete
canonical corpus plus the new promotion staging records:

```bash
spokenform-gold split \
  data/train data/dev data/test \
  "$SPOKENFORM_GOLD_WORK/promotion_staging/batch-0001.jsonl" \
  --registry splits/family_assignments.json \
  --out-root "$SPOKENFORM_GOLD_WORK/canonical-next"
```

Inspect the split-registry diff before copying the generated `train/dev/test`
files into Git. Existing family assignments are immutable.

After merging, run:

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

Then regenerate candidate ranking against the updated reviewed corpus before
starting the next batch.

## Release ladder

Use maturity levels deliberately.

### Candidate release

A candidate release is the practical next milestone. Build it after each
meaningful reviewed-data increment:

```bash
spokenform-gold release-check \
  --version 0.x.y-candidate.N \
  --data data/train data/dev data/test \
  --controls data/controls \
  --maturity candidate \
  --out "$SPOKENFORM_GOLD_WORK/releases/0.x.y-candidate.N"
```

A candidate release is suitable for integration testing with Spokenform, but it
is not a claim that all stable coverage and review requirements are complete.

### Stable release

Before declaring stable, require:

```bash
spokenform-gold gold-audit data/train data/dev data/test --strict
```

and then:

```bash
spokenform-gold release-check \
  --version X.Y.Z \
  --data data/train data/dev data/test \
  --controls data/controls \
  --maturity stable \
  --coverage-profile stable \
  --out "$SPOKENFORM_GOLD_WORK/releases/X.Y.Z"
```

Do not weaken stable gates to make a release pass. Fix review evidence,
coverage, controls, provenance, or policy instead.

## Spokenform integration

Spokenform should consume an immutable Gold release, never the candidate work
directory.

During development, test a local release explicitly:

```bash
python -m benchmarks.spokenform_gold \
  --gold-root "$SPOKENFORM_GOLD_WORK/releases/0.x.y-candidate.N" \
  --split test
```

Only after the release is accepted should the Spokenform repository update its
pinned Gold commit/release constants and tests. Keep the default benchmark on
the held-out `test` split.

When Gold starts shipping a populated `data/train`, confirm that Spokenform's
release materialization contract intentionally includes or excludes that split;
do not let `--split all` silently change meaning.

## Coverage-driven stopping rule

Do not define "full" as a fixed row count. Define it by release gates and
coverage.

After every batch, inspect remaining gaps and select the next batch from those
gaps. Prioritize:

1. missing stable-required category or surface pattern;
2. missing language for an existing category;
3. negative controls in high false-positive-risk families;
4. ambiguity examples;
5. cross-source disagreements;
6. rare multi-unit and boundary cases;
7. only then more examples of already well-covered shapes.

The stable target is reached when strict oracle/review audit passes, stable
release-check passes without allowed-gap exceptions, the control suite passes,
and the held-out Spokenform benchmark can consume the immutable release.

## Agent deliverables for each data-growth batch

A coding/annotation agent should leave behind a concise machine-readable and
human-readable handoff containing:

```text
source revisions used
ingestion row-accounting summary
candidate count and exclusion count
coverage gaps before
selected review batch IDs
review/adjudication status
promotion disposition counts
new/changed family assignments
coverage gaps after
candidate/stable release-check result
Spokenform benchmark result on the resulting release
unresolved source or semantic conflicts
```

The agent must not claim completion when only candidate import or annotation
proposals exist.

---
# When an agent encounters uncertainty

If a source record appears wrong:

```text
do not fix silently
→ preserve source
→ quarantine
→ record reason
```

If two benchmarks disagree:

```text
do not majority-vote
→ identify semantic/policy difference
→ create conflict/adjudication item
```

If an example is ambiguous:

```text
do not invent missing context
→ mark ambiguous
```

If a new rule fixes one case but may broaden matching:

```text
add negative controls
```

If benchmark coverage is low:

```text
do not lower the target
→ add or discover data
```

If current Spokenform disagrees with gold:

```text
do not adapt gold to implementation
→ investigate implementation or policy
```

If policy itself is wrong:

```text
make an explicit policy-change proposal
→ document impact
→ version appropriately
```

---

# Definition of done for ordinary changes

A code or data task is not complete until:

1. the change preserves benchmark invariants;
2. relevant tests exist;
3. `make check` passes;
4. source provenance is intact;
5. new ambiguity is represented explicitly;
6. false-positive risk was considered;
7. coverage impact was considered;
8. documentation is updated when behavior or policy changes.

---

# Final instruction

Optimize this repository for **benchmark integrity**, not for making Spokenform's
current score look better.

When forced to choose between:

```text
a cleaner leaderboard
```

and:

```text
a benchmark that exposes a real weakness
```

choose the benchmark that exposes the real weakness.
