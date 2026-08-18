# Source policy

PolyNorm, async-TN and Proteno remain external benchmark sources.

MVP rules:

- never silently rewrite an upstream record;
- import source examples into `data/candidates/`, not directly into gold;
- record benchmark name and source identifier;
- preserve upstream expected text in provenance where available;
- keep source-manifest `license_id`, `license_scope`,
  `redistribution_status`, and `materialization_policy` aligned with the
  actual upstream source scope you are importing;
- public release checks validate only the source entries referenced by the
  release records, but those referenced entries must be mechanically valid;
- `metadata_only` and `not_redistributable` sources must stay in
  source-backed/external-ref form for public releases;
- `review_required` source entries block public release materialization until a
  maintainer records a conscious policy decision;
- do not redistribute full upstream corpora until license compatibility and
  attribution requirements are reviewed;
- quarantine suspicious language/transcription/annotation rows instead of
  treating an automated judge as authoritative.

Current source pointers:

- PolyNorm → official locale JSONL files under `polynorm_bench/*/*_groundtruth.jsonl`
- Proteno → paired `unnorm_list.pkl` / `norm_list.pkl` files per language
- async-TN → Async's public Hugging Face pronunciation benchmark download
  bundle, with repository-local schema fixtures pinned in
  `tests/fixtures/importers/`

For restricted upstream corpora, prefer this lifecycle:

```text
local upstream bundle
        +
Spokenform Gold overlay / external_ref record
        ↓
local hydrated benchmark
```

## Scaled ingestion policy

The current Async Space revision is pinned by its immutable commit in `sources/manifest.json`. The importer prefers `data/sentences.json` and `data/multilingual-sentences.json`, while retaining compatibility with the older fixture bundle schema. Evaluation result CSVs are recovery inputs only and must not be used to invent missing multilingual unit metadata.

Importer reports must account for every row as a candidate, a metadata-only candidate, or an explicit exclusion. Reports include source hashes, schema, languages, locales, categories, surface patterns, mapping status, multi-unit counts, and exclusion reasons.

Candidate deduplication is source-independent. Exact input matches retain all source identities, same-input and different-output groups are conflicts, and source overlap is reported before coverage counts are interpreted. Family clustering creates deterministic review suggestions only. Stable family IDs and split assignments belong to reviewed promotion.

The repository records source metadata and hashes in `sources/source-lock.json` without embedding restricted full PolyNorm or Proteno corpora. Proteno English, Spanish, and Tamil remain separate source identities and license scopes. Tamil is not part of the current six-language release target.
