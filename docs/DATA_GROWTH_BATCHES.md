# Data-growth batches 0–2

The supported entry point for a new batch is `batch-create`. It owns source staging under the batch root and reports input, filtering, clustering, and selection counts.

This document is the operational boundary for the first full-dataset production
cycle. It complements the source, annotation, promotion, and release policies.

## Batch 0 — repository and process hygiene

- Run the complete tests and repository checks.
- Confirm the Proteno official fixtures are present and deterministic.
- Keep canonical release materialization inclusive of train/dev/test.
- Keep normal benchmark evaluation held out on test unless a caller selects
  another split explicitly.
- Record that the strict Spokenform adapter and immutable Gold pin live in the
  companion Spokenform repository and are updated only after an accepted release.

A stale plan may describe fixture failures that are already resolved in the
current checkout. Do not manufacture a code change for a failure that cannot be
reproduced; add regression coverage and report the baseline instead.

## Batch 1 — stable-required coverage preparation

Use the pinned external source cache when available. For a local deterministic
smoke run, checked-in fixtures may be copied into a disposable cache. Run
`ingest-upstreams` with an explicit batch name, inspect row accounting, source
revisions, exclusions, deduplication, conflicts, coverage, and ranking, then
create blind reviewer A/B artifacts.

Every imported row remains `split=candidate` and `status=quarantine`. A ranker,
LLM proposal, or upstream expected output is not a review decision. Promotion
requires independent reviews, adjudication, a full sentence oracle, a stable
family ID, and a source/materialization decision.

Prioritize missing stable-required categories and patterns, then missing language
coverage and nearby negative controls. Do not lower targets to make the report
look complete.

## Batch 2 — multilingual breadth and Czech

Recompute the ranking after each reviewed promotion. Add multilingual families
and nearby no-change/ambiguity controls where false positives are plausible.
Czech is a required target but is not supplied by the current supported upstream
ingestion path; it remains an explicit gap until independently authored and
reviewed records are available. Do not fill Czech by unreviewed translation.

## Handoff contract

A batch handoff records:

- source revisions and source-cache availability;
- shard row accounting, candidate count, and exclusion count;
- coverage gaps before and after the batch;
- selected batch IDs and review/adjudication state;
- promotion dispositions and any new family/split assignments;
- candidate/stable release-check result and benchmark availability;
- unresolved source, semantic, review, Czech, or companion-repository blockers.

If only proposals or blind artifacts exist, the handoff must say so and must not
claim a complete or stable Gold dataset.
