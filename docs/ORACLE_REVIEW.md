# Sentence Oracle Review Artifacts

Use the blind review command to create independent reviewer inputs:

```bash
spokenform-gold blind-review data/candidates/*.jsonl --reviewer-slot A --out review-a.jsonl
spokenform-gold blind-review data/candidates/*.jsonl --reviewer-slot B --out review-b.jsonl
```

The generated artifact intentionally omits upstream expected output and leaves `annotation` empty. Reviewers fill the same sentence-oracle shape independently. An adjudicator may compare the two completed annotations and reveal source expectations only after both first passes are complete.

A completed review should record `review_schema_version`, a lifecycle `review.status`, at least two independent reviewers, an adjudicator, a protocol version, structured disagreement dimensions, and any source error reason codes.
