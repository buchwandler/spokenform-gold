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
- add HTML dashboard
- add private challenge split

## Ingestion hardening completed

- deterministic surface-pattern inference for coverage reporting
- source row accounting and import diagnostics
- immutable source-lock metadata
- cross-source candidate fingerprints and duplicate lineage reports
- conservative family-clustering suggestions before promotion

## Next ingestion work

- fetch pinned upstream bundles into external source caches
- rank candidates by coverage deficit, ambiguity, negative-control need, and source disagreement
- independently adjudicate candidates and assign Spokenform-owned family IDs
- promote only reviewed, license-compatible records into experimental release data
