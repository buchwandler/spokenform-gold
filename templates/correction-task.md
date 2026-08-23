# Spokenform Gold correction task: `<RECORD_ID>`

You are preparing a targeted correction for exactly the canonical Gold record
identified by `record.id` above.

## Human-interface contract

- Resolve all machine artifacts from `record.id` and the generated context.
- Do not ask the human to open or edit JSONL.
- Do not ask the human to identify A/B rows, comparison rows, or artifact paths.
- `record.id` is the permanent canonical correction handle.

## Required context

Read `context.json`, inspect the current canonical record, the latest review
lineage, A/B evidence, comparison, adjudication, source references permitted by
policy, and the registered taxonomy/policy definitions. Determine whether the
reported problem is valid under benchmark policy; do not adapt Gold to current
Spokenform output.

## Required correction procedure

1. Preserve the exact `record.id`.
2. Preserve `family_id` and source identity unless an explicit migration or
   supersession decision proves they are wrong.
3. Propose corrected semantic/oracle data, including explicit accepted and
   rejected variants.
4. Emit a complete `oracle-correction` artifact in `decision.json` with old and
   new oracle hashes, review revision, reviewers, adjudicator, reason, and
   review-evidence lineage hashes.
5. Validate the proposed record before replacing any canonical data.
6. Preserve the old review evidence and append a new correction revision.
7. Regenerate `report.html` and inspect the corrected record through its stable
   deep link.

The input may change, which may produce a new derived `sentence_oracle_id`.
That does not permit changing the permanent `record.id`, and historical review
evidence must not be rewritten.
