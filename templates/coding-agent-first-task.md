# Coding Agent — First Task Template

> Operational template for the Spokenform Gold production workflow. See `docs/DATA_GROWTH_BATCHES.md` and `docs/ANNOTATION.md`.

---

You are working in the spokenform-gold repository.

Goal:
Prepare the repository for the first production Gold-data batch. Do not attempt
to complete the entire benchmark in one run and do not promote unreviewed
upstream data.

Read first:

- AGENTS.md
- README.md
- DATA_MODEL.md
- docs/ANNOTATION.md
- docs/ORACLE_REVIEW.md
- docs/PROMOTION.md
- docs/SOURCE_POLICY.md
- docs/DATA_GROWTH_BATCHES.md
- taxonomy/coverage_targets.json
- taxonomy/release_maturity_profiles.json
- sources/manifest.json

Tasks:

1. Establish the real baseline.

   - Run the full test suite.
   - Run canonical validation, gold-audit, coverage, control validation, and
     control coverage.
   - Build a candidate release from train/dev/test + controls.
   - Record exact counts and failures.
   - Do not modify code for failures that exist only because an external
     context pack omitted binary fixtures; verify the real checkout.

2. Verify source-cache readiness.

   - Check async_tn, polynorm, and proteno against the revisions pinned in
     sources/manifest.json.
   - Do not fetch or vendor source data into the Git repository.
   - Report missing paths/revisions explicitly.

3. Run the first full-source ingestion, if the source cache is complete.

   - Use ingest-upstreams with batch-0001, limit 100.
   - Use en/de/es/fr/it/pt.
   - Rank against data/train data/dev data/test.
   - Preserve every imported row as quarantine/candidate material.
   - Inspect and report row accounting, exclusions, dedupe groups, conflicts,
     family suggestions, coverage-before, and selected review IDs.

4. Exercise the existing strict-review upgrade path for the existing 62
   canonical records.

   - The current records are legacy_review and stable audit requires two
     independent reviewers plus an adjudicator.
   - Use the existing deterministic workflow for completed blind-review A/B
     artifacts, comparison, adjudication, and application to canonical records.
   - Use the existing CLI path to compare completed A/B sentence-oracle
     reviews.
   - Do not reimplement the review framework; report a concrete production
     blocker if the existing workflow fails.

5. Produce blind review inputs, but do not fill them using upstream expected
   output.

   - Existing canonical corpus: reviewer A and reviewer B.
   - New batch-0001: reviewer A and reviewer B.
   - Ensure source.upstream_expected and current Spokenform prediction are not
     exposed in first-pass reviewer artifacts.

6. Do not promote any row unless two independent completed reviews and an
   adjudication decision exist.

7. Leave a handoff report containing:
   - test baseline;
   - source revisions and cache readiness;
   - current record/language/category/unit counts;
   - exact coverage gap breakdown;
   - ingestion row accounting;
   - candidate/exclusion/conflict counts;
   - batch-0001 IDs;
   - review tooling status;
   - artifacts created;
   - files changed;
   - commands run;
   - candidate release result;
   - unresolved blockers.

Hard rules:

- Never make Gold match current Spokenform output.
- Never treat upstream expected strings as Gold authority.
- Never majority-vote conflicting sources.
- Never weaken taxonomy/coverage/release gates to get green.
- Never invent reviewer identities.
- Never copy restricted full upstream datasets into Git.
- Never hand-pick a train/dev/test split.
- Prefer no code changes unless the production run exposes a real workflow
  blocker.

Definition of done:
A reproducible production baseline and batch-0001 review package exist, the
strict-review workflow for existing canonical records is either demonstrated
or minimally implemented, and no unreviewed candidate has been promoted.
