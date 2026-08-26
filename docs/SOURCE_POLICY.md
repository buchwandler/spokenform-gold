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

## External-cache orchestration

Use `spokenform-gold ingest-upstreams` with a source cache containing:

```text
source-cache/
  async_tn/data/sentences.json
  async_tn/data/multilingual-sentences.json
  polynorm/polynorm_bench/*/*_groundtruth.jsonl
  proteno/data/English/{unnorm_list.pkl,norm_list.pkl}
  proteno/data/Spanish/{unnorm_list.pkl,norm_list.pkl}
```

The command does not fetch data. It checks required paths, compares `git rev-parse HEAD` to the pinned manifest revision when Git metadata is present, and writes working candidates under an external work root. Each shard has JSONL candidates, an exclusions file, and a diagnostics report with `row_accounting_ok`. A false accounting result is fatal.

The orchestrator then creates deterministic merged candidates, dedupe, conflict, family-suggestion, reviewed-coverage, ranking, exclusion, pool-summary, and review-batch artifacts. Ranking and batching are triage aids only. They do not adjudicate semantics, assign release splits, or promote candidates.

The exclusion report groups observed failures by source, reason, source category, language, and surface shape. This evidence should guide narrowly scoped importer or mapping changes. Do not broaden recognizers or mappings from hypothetical cases.

All source-derived rows remain quarantine candidates. Source policies, licenses, materialization policies, `release_ready`, upstream expected text, and source identity are not changed by ingestion.

## Fixture-derived candidate expansion

The repository may include small candidate shards generated directly from checked-in importer fixtures. This does not grant permission to embed complete third-party corpora. The current fixture expansion contains eight Async records and six PolyNorm records, including raw and official PolyNorm projections where their source identities remain distinct.

Every fixture-derived row remains `split=candidate` and `status=quarantine`, retains `source.upstream_expected`, source IDs, source hashes, and source revisions, and must pass the normal validator. Metadata-only rows remain visible when a source category is unsupported. Do not change `release_ready`, `materialization_policy`, or license scope as part of fixture expansion.

For full upstream refreshes, fetch the pinned revisions outside Git, run `ingest-upstreams`, inspect row-accounting and exclusion reports, then run dedupe, conflicts, family suggestions, coverage, ranking, and review-batch export. Review and promotion are separate human-governed steps.

## v2 source observations

The v2 corpus stores `source_observations` on the reviewed sentence. Each observation preserves benchmark, source ID, revision, upstream expectation where permitted, hashes, and materialization metadata. Multiple observations are grouped before review. `embedded` is allowed only for sources whose manifest policy permits public materialization. `external_ref` is used for restricted sources.

The collector may read external caches, but it never copies a restricted upstream corpus into Git. A source disagreement is evidence for adjudication, not a majority-vote promotion rule.
