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

## Stable review identity and lineage

`record.id` is the immutable public canonical identity and correction handle. `sentence_oracle_id` is derived from language, locale, and normalized input for review-cycle joins; it is not stored in canonical records. `candidate.id` identifies source candidate provenance. A correction may change the derived sentence identity when input changes, but must preserve the public record ID under normal correction.

Durable sanitized review provenance is stored as `review-evidence.jsonl` where policy permits. Each entry is keyed by `record_id` and `review_revision` and links candidate/source references, A/B reviewer evidence, comparison, adjudication, hashes, and correction history without publishing blind-review forbidden fields.

The human interface is generated HTML: `review-report.html` for batch review and `records.html` for release inspection. Humans identify corrections by record ID; they do not edit or enumerate JSONL rows.

## Canonical v2 corpus

The authoring source of truth is `data/corpus.jsonl`. A v2 record has one permanent `id`, `family_id`, language, locale, input, explicit oracle, units, status, and plural `source_observations`. It has no `split` and no duplicate `expected_output` state. Consumers can call the optional family-safe export helper to create train, dev, and test views without changing canonical records.

A case identity is the conservative tuple `(language, locale, normalized input)`. A source identity is `(benchmark, source_version, source_id)`. All observations in one case move together through independent reviewer A, independent reviewer B, and one adjudicator. Synthetic sentences remain candidates until that same review path is completed.

v2 releases contain `corpus.jsonl`. The loader remains compatible with v1 releases that contain split directories.
