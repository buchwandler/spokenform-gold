# Sentence Oracle Review Artifacts

Use the blind review command to create independent reviewer inputs:

```bash
spokenform-gold blind-review data/candidates/*.jsonl --reviewer-slot A --out review-a.jsonl
spokenform-gold blind-review data/candidates/*.jsonl --reviewer-slot B --out review-b.jsonl
```

The generated artifact intentionally omits upstream expected output and leaves `annotation` empty. Reviewers fill the same sentence-oracle shape independently. An adjudicator may compare the two completed annotations and reveal source expectations only after both first passes are complete.

A completed review should record `review_schema_version`, a lifecycle `review.status`, at least two independent reviewers, an adjudicator, a protocol version, structured disagreement dimensions, and any source error reason codes.


## Applying completed A/B evidence

The strict re-review commands are:

```bash
python -m spokenform_gold.cli compare-reviews REVIEW_A.jsonl REVIEW_B.jsonl \
  --out comparison.jsonl

python -m spokenform_gold.cli apply-reviewed-oracles \
  --records data/train data/dev data/test \
  --review-a REVIEW_A.jsonl \
  --review-b REVIEW_B.jsonl \
  --decisions decisions.jsonl \
  --out-root ../spokenform-gold-work/canonical-reviewed
```

compare-reviews requires completed annotations, a stable reviewer_id for
each slot, matching sentence-oracle IDs, and matching input/language/locale.
It rejects shared reviewer identities and fields that would expose upstream
expectations or current Spokenform output.

apply-reviewed-oracles requires one adjudicated decision per canonical
sentence-oracle identity. It preserves the original record ID, family ID, and
source provenance; recomputes oracle_hash; records reviewers, adjudicator,
protocol, disagreement dimensions, and source-error codes; validates every
result; and writes a new isolated output tree. It refuses family migration,
context mismatch, missing decisions, invalid review status, and output paths
that overlap canonical inputs.

The generated blind artifacts intentionally have empty annotations and no
reviewer identity. They are preparation artifacts only. Human A/B review and
adjudication remain required before any legacy record can pass strict Gold
audit. Do not use this workflow to invent evidence, copy restricted upstream
text into public Gold, or adapt Gold to current Spokenform output.
