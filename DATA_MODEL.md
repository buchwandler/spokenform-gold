# Data model

The JSONL record is the stable interchange unit.

Important invariants:

- `source` is mandatory, including for locally curated records.
- `family_id` is mandatory so similar templates do not leak across splits.
- `schema_version`, `taxonomy_version`, and `policy_version` are mandatory.
- `expected_output` can be null only for `ambiguous` and `quarantine`.
- a reviewed unit's `canonical` realization must occur in `accepted`.
- duplicate surface strings require explicit `start`/`end` offsets.
- negative controls use `status=no_change`, no units, and `negative_for`.
- ambiguity is represented explicitly instead of being hidden in judge prompts.

The canonical release pipeline also requires:

- source manifests keyed by `source.benchmark`;
- versioned policy and ambiguity registries;
- deterministic split assignment by `family_id`;
- prediction files keyed by record `id`, not row order.

## Configuration controls

Configuration-sensitive assertions use the separate control-record format in `schemas/control-record.schema.json`. A control record references fixed profile IDs from `taxonomy/evaluation_profiles.json`; it never embeds arbitrary runtime kwargs. Each profile expectation may declare an expected output plus required and forbidden benchmark-facing ownership rules. Control output, ownership, false-positive, language, and suite metrics are reported separately from canonical semantic Gold.

## Split and candidate boundaries

Canonical records use the frozen family-safe `train`, `dev`, and `test` assignments. The default assignment ratios are 70% train, 15% dev, and 15% test, but an existing family assignment always takes precedence over hash-based allocation. Existing families must not be moved to populate a newly added split.

Candidate records use `split=candidate` and are never release data. Candidate regression rows may have null `expected_output` and unadjudicated policies, but must retain source identity, source version, source URL, source hash where applicable, and enough unit metadata for independent review.

## Release split contract

A release includes all canonical records from `train`, `dev`, and `test`, with
frozen family assignments and no candidate rows. The benchmark runner's default
held-out evaluation is `test`; callers that need `train`, `dev`, or `all` must
select that split explicitly. A populated train shard therefore changes release
contents but does not change the default benchmark target.

Batch review artifacts use explicit names such as `batch-0001.jsonl` and live
outside canonical data. Their rows remain `split=candidate` and
`status=quarantine` until the promotion evidence and source policy gates pass.
