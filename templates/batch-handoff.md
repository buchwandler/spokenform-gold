# v2 Batch Handoff

Use this compact handoff for one logical batch. Put detailed artifacts in files,
not in this document. Use `NONE`, `NOT_RUN`, or `NOT_PUBLISHED` explicitly.

- batch_id:
- repository commit:
- source-lock hash:
- case count:
- reviewer A identity:
- reviewer A complete count:
- reviewer A artifact hash:
- reviewer B identity:
- reviewer B complete count:
- reviewer B artifact hash:
- review-check: ready/issues count
- adjudicator identity:
- accept/exclude/unresolved counts:
- integrated record count:
- corpus count before/after:
- validation result:
- coverage summary before/after:
- report.html path:
- blockers:
- next action:

The generated `review-report.html` is the human review surface.
Do not include full case-ID lists, disagreements, source observations, or JSONL
rows. The human receives this summary and generated HTML reports. A/B
disagreement alone is not a blocker when adjudication resolved it; name any
`needs_review` blocker and attempted resolution explicitly.
