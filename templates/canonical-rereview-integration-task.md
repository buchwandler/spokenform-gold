# Canonical Re-review Integration — Mechanical Task Template

> Use only after canonical adjudication has produced complete decisions and
> `review-preflight` plus `compare-reviews` have passed. This role must not make
> new semantic judgments.

## Inputs

```text
canonical records: <ABSOLUTE_PATHS_TO_DATA_TRAIN_DEV_TEST>
completed review A: <ABSOLUTE_PATH_TO_CANONICAL_A_COMPLETE_JSONL>
completed review B: <ABSOLUTE_PATH_TO_CANONICAL_B_COMPLETE_JSONL>
decisions: <ABSOLUTE_PATH_TO_CANONICAL_DECISIONS_JSONL>
comparison: <ABSOLUTE_PATH_TO_COMPARISON_JSONL>
family registry: splits/family_assignments.json
output root: <ABSOLUTE_WORK_ROOT>/reviews/canonical/integration
```

Do not overwrite canonical data or review artifacts. Keep every generated file
under the isolated output root until explicit approval is granted.

## Mechanical sequence

1. Run `spokenform-gold review-preflight` against the exact named records and
   completed A/B files. Stop if it is not ready.
2. Run `spokenform-gold compare-reviews` and verify the comparison hash matches
   the adjudication handoff.
3. Run `spokenform-gold apply-reviewed-oracles` with `--out-root` below the
   isolated work root.
4. Verify output isolation, record IDs, family IDs, source provenance, and
   frozen family assignments are unchanged.
5. Run `spokenform-gold oracle-diff` against the canonical inputs and inspect
   only the intended oracle/review metadata changes.
6. Restore deterministic `train`, `dev`, and `test` shards with the frozen
   family splitter; never hand-pick a split.
7. Run strict validation, Gold audit, conflict checks, and coverage checks.
8. Obtain explicit approval before copying generated canonical shards into Git.
9. Stage and commit explicit paths only; never use `git add .`.

## Prohibited actions

- Do not reinterpret semantics, edit decisions, or fill missing annotations.
- Do not derive Gold from current Spokenform output.
- Do not change taxonomy, policy, source identity, family assignment, or review
  independence in this context.
- Do not copy into `data/train`, `data/dev`, or `data/test` before approval.
- Do not publish or update downstream Spokenform pins.

## Handoff report

Record the exact commands, output paths, hashes, oracle diff, family-registry
diff, validation/audit results, approval status, copied paths, and commit hash.
