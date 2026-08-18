# Data model

The JSONL record is the stable interchange unit.

Important invariants:

- `source` is mandatory, including for locally curated records.
- `family_id` is mandatory so similar templates do not leak across splits.
- `expected_output` can be null only for `ambiguous` and `quarantine`.
- a reviewed unit's `canonical` realization must occur in `accepted`.
- duplicate surface strings require explicit `start`/`end` offsets.
- negative controls use `status=no_change`, no units, and `negative_for`.
- ambiguity is represented explicitly instead of being hidden in judge prompts.
