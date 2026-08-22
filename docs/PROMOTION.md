# Reviewed promotion workflow

`promote-reviewed` is the boundary between external candidate work and the
Git-tracked canonical benchmark across `data/train`, `data/dev`, and
`data/test`. It writes staging JSONL and an audit report. It never modifies any
canonical shard or the split registry.

## Required review evidence

Every candidate in the input batch must have exactly one decision. A promotion
decision requires two independent reviewers, an adjudicator, a Spokenform-owned
`family_id`, a release-eligible status, and an explicit `license_disposition`.
The decision must include the reviewed input, expected output, units,
negative-control metadata, and notes.

The dispositions are:

- `promote_curated`: create an independently authored
  `spokenform_curated` record and preserve upstream references as lineage;
- `promote_upstream`: retain the upstream source identity and require that its
  manifest explicitly permits embedded public redistribution;
- `keep_external`: keep the candidate outside the canonical staging output;
- `reject`, `quarantine`, and `needs_review`: keep the candidate out of Gold.

Imported family suggestions are not accepted as final family identity. The
review decision must provide the Spokenform family explicitly. Promoted records
start with `split=candidate`; run the family-aware `split` command after review
and before merging them into canonical data.

## Command

```bash
spokenform-gold promote-reviewed \
  --candidates "$SPOKENFORM_GOLD_WORK/candidates/review-batch.jsonl" \
  --decisions "$SPOKENFORM_GOLD_WORK/reviews/decisions.jsonl" \
  --against data/train data/dev data/test \
  --out "$SPOKENFORM_GOLD_WORK/promotion_staging/reviewed.jsonl" \
  --report "$SPOKENFORM_GOLD_WORK/promotion_staging/promotion-report.json"
```

The command fails closed for missing or duplicate decisions, invalid reviewed
records, duplicate IDs, family language or locale conflicts, and restricted
source materialization. The report is deterministically sorted and records
candidate, decision, disposition, source, language, family, and license counts.

## Canonical merge gates

After promotion staging:

1. split the combined current and promoted records with the frozen registry;
2. validate every resulting shard;
3. inspect unit conflicts and coverage impact;
4. validate controls separately;
5. inspect the Git diff;
6. build an experimental release with `release-check`.

Do not put source caches, candidate pools, review traces, or promotion reports
into Git unless a separate policy explicitly requires a small audit artifact.
Do not promote rows because an automated judge marked them acceptable. Preserve
upstream provenance and source policy throughout the workflow.

## Current review boundary

The external work area currently contains a 100-record ranked review batch and
30 proposals from each of two annotator passes. The adjudication report records
`proposal_only_no_independent_human_reviewer`, unresolved semantic and canonical
fields, and `quarantine=30`, with zero promoted records. These proposals remain
`data/train`, `data/dev`, or `data/test` until independent human review,
adjudication, stable Spokenform family assignment, and source-policy decisions
are complete.

## Sentence-oracle promotion boundary

A promotable decision must include an explicit `oracle` object with full-sentence `canonical_output`, `accepted_outputs`, `rejected_outputs`, and `variant_mode: explicit`. Promotion copies this reviewed assertion; it does not derive sentence variants from unit alternatives. Decisions may include `review_protocol_version`, structured `disagreement`, and `source_error_codes`.

Two independent reviewer IDs and one adjudicator are required for promotion decisions. Historic migration rows may carry `review.status=legacy_review` without invented identities, but stable release rejects them until re-reviewed. Upstream expected output remains provenance evidence and is hidden from first-pass reviewers.

## Batch promotion boundary

Batch preparation may produce ranked candidates, blind review inputs, coverage
reports, and an empty or provisional decision queue. It may not promote a row
without two independent reviewer IDs, an adjudicator, a full sentence oracle,
a Spokenform-owned family ID, and an explicit license/materialization decision.

When the source cache or independent review evidence is unavailable, the correct
batch result is a quarantine-only handoff that names the blocker. A candidate
release can be built from eligible reviewed data; a stable release cannot be
claimed from proposals alone.
