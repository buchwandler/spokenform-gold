# Roadmap

## MVP

- JSONL canonical record model
- mechanical validator
- async-TN candidate importer with current English and multilingual schema support
- unit-level contradiction detector
- coverage target report
- unseen-shape discovery from real text
- sample judge-gold format
- tests

## Next

- broaden reviewed corpus coverage beyond the current experimental English/German/Spanish batch
- raise the release maturity gate from experimental toward candidate/stable coverage profiles
- add richer semantic validators beyond the initial high-risk categories
- improve multi-unit scoring granularity and richer failure analytics
- add adjudication workflow UX on top of the deterministic queue
- add pluggable semantic judge
- add judge calibration report
- add private challenge split

## Ingestion hardening completed

- deterministic surface-pattern inference for coverage reporting
- source row accounting and import diagnostics
- immutable source-lock metadata
- cross-source candidate fingerprints and duplicate lineage reports
- conservative family-clustering suggestions before promotion

## Ingestion hardening completed

- deterministic external-cache orchestration for Async, PolyNorm, and Proteno supported shards
- deterministic candidate merging with duplicate-ID protection
- coverage-aware candidate ranking with conflict and duplicate lineage reasons
- exclusion grouping and candidate-pool yield summaries
- balanced review-batch export that preserves quarantine status

## Next ingestion work

- fetch pinned upstream bundles into external source caches
- independently adjudicate candidates and assign Spokenform-owned family IDs
- promote only reviewed, license-compatible records into experimental release data

## Fixture expansion completed

- expanded checked-in Async candidates from the English fixture plus six multilingual fixture rows;
- expanded checked-in PolyNorm candidates from raw and official fixture projections while preserving duplicate lineage and metadata-only exclusions;
- kept all imported rows quarantined and source-policy decisions unchanged;
- documented the external-cache refresh and pool-statistics workflow.

## Data-growth execution status

- Exercised the external-cache orchestrator with local fixture layouts for Async, PolyNorm, and Proteno; all five generated shards passed row accounting.
- Generated a 17-record merged quarantine pool, deterministic dedupe/conflict/family/ranking/exclusion/pool reports, and a 17-record review batch.
- Recorded one explicit PolyNorm unsupported-category exclusion and zero candidate conflicts. No candidate was promoted.
- Reviewed coverage remains 62 records, 15 categories, and 390 visible gaps. The gaps are not suppressed to satisfy release gates.
- Hardened stable release coverage semantics so `allow_coverage_gaps: false` rejects all remaining gaps unless explicit allowed-gap fields are configured.
- Remaining work is external source-cache refresh, independent semantic adjudication, family assignment, license review, and reviewed promotion.

## Batches 0–2 execution boundary

The current data-growth milestone is bounded as follows:

- Batch 0: verify repository checks, deterministic fixture behavior, release
  split semantics, reviewer policy, and integration boundaries.
- Batch 1: rank and review candidates for stable-required categories and patterns;
  do not promote source rows without independent adjudication.
- Batch 2: expand reviewed multilingual coverage and add Czech only from
  independently authored/reviewed material; report the gap when it is absent.

A batch handoff must include source revisions/availability, row accounting,
candidate and exclusion counts, coverage before/after, review state, promotion
dispositions, family/split changes, release result, benchmark availability, and
unresolved conflicts. It must distinguish candidate preparation from Gold
completion.


## Sentence-centric workflow implemented

The v2 migration provides `data/corpus.jsonl`, compatibility loading for old split releases, deterministic family-safe export, source-observation clustering, independent A/B review checks, direct atomic integration, and HTML corpus reporting. The former split, promotion, ranking, and maturity machinery remains available only where compatibility or optional release policy requires it.

Remaining data growth is still review work. The code does not fabricate a 100-case review batch, adjudication, or synthetic Gold records.
