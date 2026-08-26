# Spokenform Gold v2 correction: `<RECORD_ID>`

Prepare a targeted correction for exactly the canonical record identified by
`record.id`.

## Human interface

The human supplies `record.id`. Tools resolve review evidence, source
references, hashes, and correction history. Do not ask the human to inspect or
edit JSONL, identify artifact paths, or enumerate review rows.

## Scope

The canonical authoring source is the `data/corpus/` directory, with one language shard per `data/corpus/<language>.jsonl`. This is a v2 correction,
not a split-based authoring operation. Preserve the permanent `record.id`,
family identity, and source identity unless an explicit supersession decision
proves one is wrong. Do not adapt Gold to current Spokenform output.

## Procedure

1. Resolve the current record and latest review lineage from `record.id`.
2. Determine the policy-valid semantic/oracle correction, including explicit
   accepted and rejected variants.
3. Write a complete artifact conforming to
   `schemas/oracle-correction.schema.json` with `record_id`, old and new oracle
   hashes, reason, reviewers, adjudicator, review lineage hashes, and
   `new_record`.
4. Validate the proposed record before changing the corpus.
5. Preserve prior evidence, append a correction revision, and regenerate the
   HTML report.

A changed input may change derived review evidence, but it never permits silent
mutation of the permanent record ID. Report the record ID, decision, evidence
hashes, validation result, and generated report path.
