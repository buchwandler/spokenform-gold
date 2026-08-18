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
