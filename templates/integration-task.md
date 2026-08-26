# v2 Mechanical Integration

Run only after complete independent reviews and a ready review-check. This role
must not reinterpret semantics or open unrelated source/history artifacts.

Inputs:

- batch root
- review-check summary path
- adjudicated.jsonl path
- canonical corpus path

```bash
spokenform-gold review-check \
  --batch <BATCH_ROOT> \
  --review-a <A_COMPLETE> \
  --review-b <B_COMPLETE> \
  --json <REVIEW_CHECK_JSON>

spokenform-gold integrate \
  --batch <BATCH_ROOT> \
  --corpus data/corpus.jsonl

spokenform-gold integrate \
  --batch <BATCH_ROOT> \
  --corpus data/corpus.jsonl \
  --write

spokenform-gold validate data/corpus.jsonl
spokenform-gold report --records data/corpus.jsonl --out <REPORT.html>
```

The dry run must pass before `--write`. Preserve v2 identity, source
observations, provenance, and policy. Reject incomplete or unresolved decisions.
The human receives compact counts and the generated report, not JSONL rows.
