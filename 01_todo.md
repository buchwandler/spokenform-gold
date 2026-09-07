# Spokenform Gold — First Release Finalization Brief

**Date:** 2026-09-07  
**Scope:** Review of the reconstructed `spokenform-gold` repository plus the two supplied agent-session exports, `run.html` and `run2.html`.  
**Primary objective:** Make a first public release possible **without requiring completion of the entire PolyNorm source dataset first**.

---

## 1. Executive decision

The first release should **not** be gated on reviewing all 4,300 PolyNorm examples.

The current canonical corpus is already large enough to justify a first experimental release:

- canonical records: **19,789**
- validation in the supplied run: **passed**
- strict Gold/oracle audit in the supplied run: **passed**
- review-complete according to the canonical record audit: **19,789**
- current public corpus browser: **19,789 records across 8 languages**
- tests in the supplied run: **279 passed + 16 subtests**
- current release blocker in the supplied run: **source publication policy**, not semantic corpus validity

The project should therefore adopt this release boundary:

> **Freeze the existing canonical corpus for `v0.1.0-exp`. Do not add batch-0030 or the remaining PolyNorm source rows before this release. Fix publication/source-policy mechanics, create explicit source decisions, generate a reproducible release, publish it as experimental, and continue PolyNorm completeness as a separate post-release campaign.**

This avoids turning “first release” into “perfect reconstruction of every upstream benchmark”.

The missing PolyNorm material is still valuable, but it is **data growth**, not a prerequisite for publishing the already-reviewed canonical benchmark.

---

## 2. What the two runs show

### 2.1 `run.html`: the corpus itself is not the main blocker

The first run reported:

- repository clean and synchronized
- canonical corpus: **19,789**
- review gaps: **0**
- validation: passed
- tests: passed
- latest ordinary batches finalized through batch-0029
- release preflight:
  - canonical records: **19,789**
  - embedded: **62**
  - blocked: **19,727**
  - blocker: `source_policy_unresolved`

This is the key distinction:

> The corpus is usable locally; publication is blocked by source materialization/governance.

The run then investigated PolyNorm and established that “PolyNorm” in the records is the upstream source identity, not a second fully re-reviewed benchmark artifact.

### 2.2 PolyNorm census from `run.html`

The pinned PolyNorm revision contains **4,300** rows, not 4,320 or 4,350:

| Locale    | Upstream rows | Exact canonical source IDs |   Missing |
| --------- | ------------: | -------------------------: | --------: |
| de-DE     |           540 |                        340 |       200 |
| en-US     |           540 |                        340 |       200 |
| es-MX     |           540 |                        320 |       220 |
| fr-FR     |           540 |                        340 |       200 |
| it-IT     |           520 |                        320 |       200 |
| ja-JP     |           540 |                         80 |       460 |
| lt-LT     |           540 |                          0 |       540 |
| zh-CN     |           540 |                        340 |       200 |
| **Total** |     **4,300** |                  **2,080** | **2,220** |

There are additionally two legacy/raw canonical source IDs (`pn-raw-1`, `pn-raw-2`) and duplicate upstream IDs in two locales. The canonical corpus therefore contains **2,083 PolyNorm-linked records**, but only **2,080 exact official source-ID matches**.

That is a source-reconciliation fact. It does **not** mean the current 19,789-record corpus must be thrown away or held indefinitely.

### 2.3 Why batch-0030 contains only 280 cases

The PolyNorm ingestion run accounted for all 4,300 rows:

- already reviewed/matched official source IDs: **2,080**
- new importable unseen observations: **280**
- importer exclusions: **1,940**
- failed/unaccounted rows: **0**

The 280-case batch is therefore not “all missing PolyNorm data”. It is only the part the current importer understands.

Batch-0030:

- 280 cases
- 260 `lt-LT`
- 20 `zh-CN`
- state: `awaiting_review`
- reviewer A: 0
- reviewer B: 0
- integrated: no

### 2.4 The 1,940 exclusions are mostly an importer vocabulary problem

All 1,940 were reported as:

```text
reason = unsupported_category
```

Observed category labels include:

- `Fractions`
- `Initialism or Acronym`
- `Vehicle or Product Code`
- `Version Numbers`
- `Unit`
- `Units`
- `Sports score`
- `URL or Email`
- `License Plate or Serial Numbers`
- `Phone Number`
- `Phone Numbers`
- `Currencies`
- `Mathematical Expressions`
- `Dates`
- `Times`
- `Cardinals`
- `Ordinal numbers`
- `Decimals`
- `Roman Numerals`
- `Abbreviations`
- `Biological Classifications`
- `Chemical Formulas`
- `Stock Tickers`
- `Hashtag or Mention`
- `Websites`

The existing mapping file understands nearby singular/canonical names such as:

- `Fraction`
- `Acronym/Initialism`
- `Vehicle/Product Code`
- `Version Number`
- `Unit (Measure)`
- `Sports Score`
- `Electronic (URL/Email)`
- `License/Serial Number`
- `Telephone`
- `Currency`
- `Mathematical Expression`
- `Date`
- `Time`
- `Cardinal`
- `Ordinal`
- `Decimal`
- `Roman Numeral`
- `Abbreviation`
- `Biological Classification`
- `Chemical Formula`
- `Stock Ticker`

This means a large part of the 1,940 exclusions is not a genuine unsupported semantic space. It is explicit source-label aliasing that has not been encoded.

`Hashtag or Mention` can plausibly map to the existing `social_handle` taxonomy category and `Websites` to `url_or_email`, but those mappings must be explicit and tested; do not silently guess them through generic string normalization.

### 2.5 `run2.html`: the present reviewer workflow does not scale safely

The second run asked one agent context to do reviewer A for all 280 cases.

The agent:

1. generated bounded review packets,
2. inspected large portions of the packet,
3. produced an “all `no_change`” annotation shortcut,
4. recognized that this would be fabricated semantic review,
5. deleted the generated result and complete artifacts,
6. left batch-0030 correctly at `review_a=0`.

This is a **good safety outcome** but a **bad workflow outcome**.

The repository prevented false Gold from surviving, but the session demonstrates that:

> “Give one agent 280 arbitrary Lithuanian/Chinese semantic review rows” is not the scalable mechanism for finishing thousands of source cases.

The correct answer is not to make the human manually review 2,220 rows. The correct answer is a resumable review campaign/harness that repeatedly assigns bounded, language-aware packets to fresh reviewer contexts and mechanically validates/merges them.

---

# 3. First-release scope

## 3.1 Freeze the canonical corpus now

For `v0.1.0-exp`:

- freeze `data/corpus/` at the current 19,789-record state;
- do not merge batch-0030 before this release;
- do not wait for the 1,940 PolyNorm category aliases;
- do not wait for 100% upstream PolyNorm row coverage;
- do not require a new A/B review of all historical canonical rows before the first experimental release.

The public release artifact may contain fewer than 19,789 records if some source policies deliberately exclude records. That is acceptable if the release manifest reports the exclusion precisely.

The canonical authoring corpus and public release materialization are already conceptually separate in the code. Use that separation.

## 3.2 Release maturity must be `experimental`

The first release should be:

```text
maturity = experimental
```

Do not label the first public artifact `stable`.

Reasons:

- not all upstream source policies are finalized;
- historical review evidence includes legacy provenance;
- PolyNorm source completeness is ~48.4% by exact official source ID;
- external-reference behavior still needs publication hardening;
- the source decision path is not sufficiently tested end-to-end.

A useful first public benchmark can still be called Gold while its **release maturity** is experimental, as long as the release notes describe the limitations.

## 3.3 Do not define release completeness as source completeness

Add a clear distinction to documentation and release metadata:

```text
canonical corpus completeness != upstream source ingestion completeness
```

For each source, report independently:

- source revision
- observed upstream rows
- rows mapped/importable
- rows represented in canonical corpus
- rows omitted from this public release
- rows excluded by importer
- source-policy decision
- materialization mode
- review-evidence class

For current PolyNorm, the first release notes should be able to say approximately:

```text
upstream rows: 4300
exact official source IDs represented in canonical corpus: 2080
unrepresented official source IDs: 2220
full-source ingestion status: incomplete
release dependency: none; remaining rows are post-release data growth
```

Do not describe the current corpus as the complete PolyNorm benchmark.

---

# 4. P0 engineering blockers before publication

The highest priority is not more annotation. It is fixing the release/source-policy implementation.

## P0.1 `release/source-release-decisions.json` is referenced by CI but absent

`.github/workflows/release.yml` invokes both:

```bash
spokenform-gold release-preflight \
  --data data/corpus/ \
  --source-decisions release/source-release-decisions.json
```

and:

```bash
spokenform-gold release \
  ... \
  --source-decisions release/source-release-decisions.json
```

The reconstructed repository does not contain that file.

### Required change

Create and commit:

```text
release/source-release-decisions.json
```

but only after the implementation issues below are fixed.

Suggested top-level structure:

```json
{
  "schema_version": "1.0.0",
  "manifest_hash": "sha256:...",
  "decisions": []
}
```

The file should be an auditable release input, not runtime cache.

---

## P0.2 `exclude_public` currently behaves like a release blocker

`source_policy.py` supports these decisions:

- `embedded_public`
- `external_ref_only`
- `exclude_public`
- `needs_human_legal_review`

But `release.plan_publication_records()` only produces:

- `embedded`
- `external_ref`
- `blocked`

`exclude_public` produces no capability, so a record whose only source is deliberately marked `exclude_public` becomes `blocked`.

That defeats the purpose of the decision.

### Required release planner model

Change the publication modes to:

```text
embedded
external_ref
excluded
blocked
```

Semantics:

- `embedded_public` → may provide an embedded publication basis
- `external_ref_only` → may provide an external-reference publication basis
- `exclude_public` → record may be deliberately omitted from the public artifact
- `needs_human_legal_review` → release blocker
- no decision / unresolved non-ready source → release blocker

For a multi-source record:

1. if any approved source can provide a legal publication basis, publish using that basis;
2. keep non-basis source references metadata-only;
3. an `exclude_public` secondary source must not block an otherwise publishable record;
4. if every source is `exclude_public`, classify the record as `excluded`;
5. if there is no publication basis and any source remains unresolved/legal-review, classify as `blocked`.

### Preflight behavior

`build_release_preflight()` should return:

```json
{
  "canonical_records": 19789,
  "embedded": ...,
  "external_ref": ...,
  "excluded": ...,
  "blocked": ...,
  "accounted": 19789,
  "ready": true
}
```

with:

```text
ready = validation_ok AND audit_ok AND blocked == 0
```

`excluded > 0` must be allowed.

Add:

```text
public_release_records = embedded + external_ref
public_excluded_records = excluded
```

to the release manifest and notes.

---

## P0.3 Source decisions affect planning but are not consistently applied to materialization enforcement

The current v2 release path can use a source decision in `plan_publication_records()`, but later `_enforce_source_materialization()` checks `sources/manifest.json` and requires `source.release_ready == true`.

That means a decision file alone is not a complete effective policy input unless the manifest has also been mutated first.

This is fragile and makes the same policy live in two places.

### Required architecture

Treat the pair:

```text
sources/manifest.json
+
release/source-release-decisions.json
```

as immutable inputs to an **effective source policy**.

Implement one helper, for example:

```python
effective_source_manifest(base_manifest, decisions) -> dict
```

It should:

- validate every decision against the same base manifest snapshot;
- reject duplicate decisions for one source;
- reject stale source revision;
- reject stale manifest hash;
- derive `release_ready`, effective materialization capability, and redistribution state in memory;
- not rewrite the base manifest during release construction.

Both:

```text
build_release_preflight()
build_corpus_release()
```

must use the same effective manifest.

Do not require `source-policy-apply --write` as a prerequisite for building a release.

---

## P0.4 Applying decisions one-by-one creates a manifest-hash chain problem

Each decision is bound to:

```text
manifest_hash
```

`source-policy-apply --write` mutates the manifest, including the source decision hash and release flags.

After applying decision A, the manifest hash changes. A decision B that was independently created against the original manifest can now become stale.

That makes “review all sources independently, then apply one at a time” unnecessarily awkward.

### Required change

Preferred:

- do not mutate the base manifest as part of normal release publication;
- keep approved decisions in `release/source-release-decisions.json`;
- compute the effective policy in memory.

Optional utility if persistence is still wanted:

```bash
spokenform-gold source-policy-apply-all \
  --decisions release/source-release-decisions.json \
  --source-manifest sources/manifest.json \
  --write
```

It must:

- validate every decision against one base manifest hash;
- apply all decisions atomically;
- write once;
- never partially update the manifest.

---

## P0.5 The external-reference overlay still copies restricted source fields

`build_v2_external_overlay()` currently deep-copies the supplied source observation:

```python
overlay["source_observations"] = [deepcopy(source)]
public_source = deepcopy(source)
```

A PolyNorm source observation may contain:

```text
upstream_expected
projection_notes
other source-derived text
```

The first run already noticed this problem.

Setting:

```json
"input": null
```

is not sufficient if other upstream text remains embedded in the release.

### Required change: explicit public-source whitelist

Do not sanitize by blacklist alone. Build a new object from a whitelist.

Example allowed provenance fields:

```text
benchmark
source_id
source_version
source_url
license
source_hash
source_file
source_split
source_category
materialization
```

Potentially allowed only after policy review:

```text
projection_notes
```

Explicitly forbidden from an external-ref public overlay:

```text
upstream_expected
original_text
normalized_text
expected
input
surface text copied from the source
raw source payload
```

Add a single helper, e.g.:

```python
public_source_reference(source: dict) -> dict
```

and use it everywhere a public external source reference is produced.

### Important legal-policy boundary

The code cannot decide whether a Gold oracle derived from a `CC BY-NC-ND` source is legally distributable.

Therefore the PolyNorm source decision must be one of:

```text
external_ref_only
exclude_public
needs_human_legal_review
```

based on the maintainer's documented policy/legal determination.

If that determination has not been made, use `exclude_public` for the first release rather than blocking all release work.

---

## P0.6 The release template and release workflow describe different publication paths

`templates/release-publish-task.md` still demonstrates:

```bash
--release-sources spokenform_curated
```

while `.github/workflows/release.yml` uses:

```bash
--source-decisions release/source-release-decisions.json
```

The old `--release-sources` path is a compatibility allowlist, not the modern policy engine.

It also selects only records whose complete source set is a subset of the requested set, which is weaker than selecting a valid publication basis on a multi-source record.

### Required change

Make the decision-based path canonical.

Update:

- `templates/release-publish-task.md`
- `README.md`
- `AGENTS.md`
- release examples/tests

to use:

```bash
spokenform-gold release-preflight \
  --data data/corpus/ \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/reports/release-preflight.json

spokenform-gold release \
  --version <VERSION> \
  --data data/corpus/ \
  --controls data/controls \
  --maturity experimental \
  --coverage-profile all-active \
  --conflict-adjudication release/conflict-adjudication.json \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/releases/<VERSION>
```

Keep `--release-sources` only as explicitly documented compatibility/debug behavior, or deprecate it.

---

# 5. Source decisions for the first release

Do **not** make these decisions automatically in code.

The implementation should support them; the maintainer approves the actual policy.

The important point is that this is a small number of **source-level decisions**, not tens of thousands of row reviews.

Current source identities include:

- `spokenform_curated`
- `spokenform_discovered`
- `spokenform_translation`
- `async_tn`
- `polynorm`
- `proteno`
- `proteno_en`
- `proteno_es`
- `proteno_ta`

### Repository-owned sources

`spokenform_curated` is already release-ready.

For repository-owned canonical records using `spokenform_discovered` or `spokenform_translation`, create explicit source decisions if they are intended for the public release.

Do not confuse the manifest description “candidate proposals” with the actual canonical record state. A source can have canonical records even if its original input file was a candidate collection. Publication policy should operate on the canonical record plus source provenance.

### PolyNorm

For the first release:

- **do not require the missing 2,220 PolyNorm rows**
- **do not require batch-0030**
- decide only whether the existing PolyNorm-derived canonical records may be represented publicly

If there is no sufficiently confident determination:

```text
decision = exclude_public
```

This must no longer block the whole release once P0.2 is fixed.

If an external-reference Gold overlay is approved:

```text
decision = external_ref_only
```

then the release code must use the sanitized public reference representation from P0.5.

### Other upstream sources

Resolve Async and Proteno at the source level in the same way.

The first release does not require ingesting every upstream row. It requires every public release record to have at least one approved publication basis.

---

# 6. Review-evidence policy for `v0.1.0-exp`

There is an apparent mismatch between two concepts:

1. the canonical audit reports all 19,789 records as review-complete;
2. the durable lineage file does not contain modern A/B artifacts for every historical record.

For PolyNorm specifically, the supplied run found:

- 349 PolyNorm-linked lineage entries
- all 349 marked `legacy_review_metadata_only`
- no modern `review_a`/`review_b` payload in those entries
- most PolyNorm canonical rows have no matching modern lineage entry

Do **not** solve this by re-reviewing all historical records before the first release.

Instead, make review provenance explicit in release reporting.

Add release metrics:

```text
review_evidence.modern_ab
review_evidence.legacy_metadata
review_evidence.missing_lineage
```

For `experimental`:

- legacy historical evidence may be allowed;
- every canonical record must still satisfy the existing strict oracle/record audit;
- disclose counts.

For a future `stable` maturity:

- define a stricter policy separately;
- if desired, require modern A/B/adjudication evidence for selected stability-critical subsets;
- do not retroactively make that a requirement for `v0.1.0-exp`.

This gives a migration path without forcing a 20,000-row re-review now.

---

# 7. PolyNorm importer repair — post-release P1

The PolyNorm importer should be repaired before restarting the full source-completion campaign.

## 7.1 Preserve original category; normalize only for mapping lookup

Add a function such as:

```python
def canonical_polynorm_category(source_category: str) -> str | None: ...
```

Use an explicit alias table.

Do not overwrite:

```text
source.source_category
```

That field must preserve the original upstream label.

Use the normalized value only to choose the taxonomy mapping.

## 7.2 Initial alias set based on the observed 1,940 exclusions

Suggested explicit aliases:

```text
Fractions                          -> Fraction
Initialism or Acronym              -> Acronym/Initialism
Initialisms or Acronyms            -> Acronym/Initialism
Vehicle or Product Code            -> Vehicle/Product Code
Vehicle or Product Codes           -> Vehicle/Product Code
Version Numbers                    -> Version Number
Unit                               -> Unit (Measure)
Units                              -> Unit (Measure)
Sports score                       -> Sports Score
Sports Scores                      -> Sports Score
URL or Email                       -> Electronic (URL/Email)
URLs or Emails                     -> Electronic (URL/Email)
URLs or emails                     -> Electronic (URL/Email)
Websites                           -> Electronic (URL/Email)
License Plate or Serial Number     -> License/Serial Number
License Plate or Serial Numbers    -> License/Serial Number
License Plates or Serial Numbers   -> License/Serial Number
Phone Number                       -> Telephone
Phone Numbers                      -> Telephone
Phone numbers                      -> Telephone
Currencies                         -> Currency
Mathematical Expressions           -> Mathematical Expression
Dates                              -> Date
Times                              -> Time
Cardinals                          -> Cardinal
Cardinal numbers                   -> Cardinal
Ordinals                           -> Ordinal
Ordinal numbers                    -> Ordinal
Decimals                           -> Decimal
Decimal numbers                    -> Decimal
Roman Numerals                     -> Roman Numeral
Abbreviations                      -> Abbreviation
Biological Classifications         -> Biological Classification
Chemical Formulas                  -> Chemical Formula
Stock Tickers                      -> Stock Ticker
Hashtag or Mention                 -> social-handle mapping
Hashtags or Mentions               -> social-handle mapping
```

For the final two, introduce a proper PolyNorm mapping entry whose canonical taxonomy category is:

```text
social_handle
```

Do not put a taxonomy category name directly into the alias table if the mapping loader expects an upstream mapping key; create a canonical upstream key such as `Hashtag/Mention` and map aliases to that key.

## 7.3 Do not promise that all 1,940 become candidates immediately

After alias repair, a row can still fail:

```text
span_unresolved
malformed_row
ambiguous span
```

That is acceptable.

The success criterion is:

> Known category-label variants must no longer be classified as `unsupported_category`.

Remaining failures should describe the real mechanical reason.

## 7.4 Add regression tests from the actual failure set

Add fixture rows for every alias family.

Tests should verify:

- source label is preserved
- normalized mapping is correct
- target taxonomy category is correct
- span resolution succeeds where expected
- row accounting remains exact
- no broad fuzzy category matching is introduced

A particularly useful test is:

```python
assert not any(
    row["reason"] == "unsupported_category"
    and row["source_category"] in KNOWN_POLYNORM_ALIASES
    for row in result.exclusions
)
```

---

# 8. Replace manual full-dataset review with a campaign harness

The repository already contains `spokenform_gold/campaign.py`, but it is not yet sufficient for autonomous source completion.

Current campaign behavior:

- records a static list of existing batch roots;
- finds the next uncompleted reviewer/adjudicator packet;
- can finalize ready batches.

What is missing:

- creating campaign batches from a source candidate pool;
- automatic result merge/validation;
- language routing;
- automatic progression to the next packet;
- robust retry/anomaly handling;
- a source-completion definition of done.

## 8.1 New campaign concept

A campaign must be created from a **frozen candidate/source snapshot**, not by “all directories currently under work/batches”.

Example:

```bash
spokenform-gold campaign-create \
  --campaign polynorm-completion-2026-09 \
  --source polynorm \
  --source-revision f3c67e047bea6b7c40bc2466c0fdaad51d8ce67d \
  --reviewed data/corpus/ \
  --batch-size 1000 \
  --languages de en es fr it ja lt zh
```

The campaign metadata should contain:

```json
{
  "campaign_id": "...",
  "source": "polynorm",
  "source_revision": "...",
  "candidate_snapshot_hash": "sha256:...",
  "canonical_corpus_hash_at_start": "sha256:...",
  "batch_size": 1000,
  "batches": [],
  "accounting": {
    "observed": 4300,
    "already_represented": 2080,
    "reviewable_unseen": 2220,
    "importer_excluded": 0
  }
}
```

After category repair, if all 2,220 become reviewable, the expected logical shape is roughly:

```text
batch 1: 1000
batch 2: 1000
batch 3: 220
```

Do not rely on that exact count until import/span resolution is rerun.

## 8.2 Batch creation should be owned by the campaign

Add:

```bash
spokenform-gold campaign-fill --campaign <ID>
```

It should:

1. read the frozen candidate snapshot;
2. remove records already represented by canonical source identity;
3. cluster sentence identities;
4. partition deterministically;
5. create new batch roots;
6. never overwrite an existing batch;
7. record the exact case/source counts in `campaign.json`.

Do not make a human create `batch-0031`, `batch-0032`, etc. manually.

## 8.3 Add campaign result merge

Add:

```bash
spokenform-gold campaign-next --campaign <ID> --role review-a
spokenform-gold campaign-merge --campaign <ID> --role review-a --result <RESULT>
```

Likewise for:

```text
review-b
adjudicator
```

`campaign-merge` should internally call the existing deterministic merge/validation functions.

The harness should not need to know packet filesystem layout.

## 8.4 Fresh-context harness loop

The external LLM harness should be able to do approximately:

```text
while campaign has reviewer-A packet:
    start fresh reviewer-A context
    provide reviewer template + one bounded blind packet
    capture result
    campaign-merge
    validate

while campaign has reviewer-B packet:
    start separate fresh reviewer-B context
    provide reviewer template + one bounded blind packet
    capture result
    campaign-merge
    validate

for every review-ready batch:
    run review-check

while campaign has adjudication packet:
    start fresh adjudicator context
    provide adjudicator template + packet
    capture result
    campaign-merge
    validate

campaign-finalize --write
validate corpus
regenerate report/site
```

No human JSONL enumeration is required.

The human inspects generated reports and supplies stable IDs for corrections.

---

# 9. Review packet sizing and language routing

The current configured maximum of 200 cases is a hard ceiling, not a required packet size.

For difficult semantic review, use smaller packets.

Suggested defaults:

```text
English/German/French/Spanish/Italian: 75–125 cases
Japanese/Chinese/Lithuanian:          30–60 cases
adjudication:                          25–75 cases
max serialized packet size:           96 KiB
```

These are starting values, not policy.

The actual packet builder must stop on either:

```text
max_cases
max_bytes
```

## 9.1 Never mix arbitrary languages merely to fill a packet

Logical batches may contain multiple languages, but generated LLM packets should preferably be language-homogeneous.

Add packet routing metadata:

```text
language
locale
case_count
estimated serialized bytes
```

The reviewer template remains blind to upstream expected outputs and other prohibited fields.

## 9.2 Reviewer capability routing

The harness should route a language only to a reviewer configuration capable of that language.

Do not ask one generic context to infer 260 Lithuanian cases if the selected reviewer cannot confidently annotate them.

Reviewer A and B must remain independent fresh contexts.

---

# 10. Add deterministic review anomaly detection

The run2 failure should become detectable before a complete artifact can be accepted.

This detector must **not** decide Gold. It only identifies suspicious review behavior and requires a fresh review.

Add a post-review check such as:

```bash
spokenform-gold review-anomaly-check \
  --batch <BATCH> \
  --review <A_COMPLETE> \
  --slot A \
  --out <REPORT>
```

Possible anomaly signals:

- 100% or near-100% identical status over a substantial heterogeneous packet;
- repeated identical rationale text for every row;
- all `no_change` on a packet known, after review isolation is over, to consist primarily of normalization-target source categories;
- units always empty despite clear numeric/symbol spans in the blind input;
- canonical output always byte-identical to input across a normalization-heavy source packet;
- one repeated oracle object across many non-identical inputs.

Important:

- this uses source/category information only **after** the blind reviewer has returned;
- it never changes an annotation automatically;
- a flagged packet is discarded and assigned to a new fresh reviewer context;
- record/case identities remain unchanged.

This would have caught the temporary “all no-change” result from run2.

---

# 11. Campaign completion criteria

A source-completion campaign should be done when every upstream row is in one explicit bucket.

For PolyNorm:

```text
represented_in_canonical
accepted_from_new_review
deferred_retry
explicit_import_exclusion
explicit_source_policy_exclusion
duplicate_source_identity
malformed_upstream
```

No row may disappear.

Report:

```text
observed = sum(all terminal/current buckets)
```

The importer already has good row-accounting behavior. Extend that idea through review and integration.

Example campaign status:

```text
source=polynorm
revision=f3c67e...
upstream=4300
already_canonical=2080
new_accepted=...
retry=...
import_excluded=...
duplicate_ids=2
unaccounted=0
```

This is much more useful than asking whether “all 4,300 have been reviewed”.

---

# 12. Corpus browser and release identity

The checked-in corpus site is already useful:

- 19,789 records
- language pages
- permanent record IDs
- GitHub issue path

Keep it.

However, the site manifest uses its own `_digest(corpus_rows)` algorithm while release/corpus status uses `canonical_corpus_hash()`.

These hashes are not directly comparable even for the same logical records.

## Required P1 improvement

Expose one canonical corpus hash everywhere.

Preferred:

```json
{
  "canonical_corpus_hash": "sha256:...",
  "site_content_hash": "sha256:..."
}
```

Use `canonical_corpus_hash()` for the first value.

Then a release note can state:

```text
canonical corpus hash at release
public release corpus hash
corpus-site source hash
```

and the human viewer can verify that the checked-in site corresponds to the intended canonical snapshot.

---

# 13. Release artifact requirements

For `v0.1.0-exp`, the release directory should contain at minimum:

```text
manifest.json
corpus.jsonl
records.html
RELEASE_NOTES.md
SHA256SUMS

sources/manifest.json
release/source decision snapshot or equivalent
source_materialization_census.json
oracle_audit.json
coverage.json
control_coverage.json
conflicts.json

taxonomy/**
schemas/**
```

Add:

```text
publication_plan.json
review_evidence_summary.json
```

if not already represented elsewhere.

## Manifest fields to require

```text
benchmark_version
maturity
canonical_corpus_hash
canonical_records
public_release_records
public_embedded_records
public_external_ref_records
public_excluded_records
public_blocked_records
source_decisions_hash
source_manifest_hash
review_evidence_summary
coverage_profile
file_hashes
```

The release build must fail if:

```text
blocked > 0
validation errors > 0
oracle audit errors > 0
unresolved unit conflicts > 0
file checksum generation fails
source decision validation fails
```

It must **not** fail merely because:

```text
excluded > 0
upstream source completeness < 100%
retry backlog > 0
```

for an experimental release, provided those facts are disclosed.

---

# 14. Required tests before first release

## 14.1 Release/source-policy tests

Add tests for:

### Decision-only release without mutating base manifest

```text
base source: release_ready=false
decision: external_ref_only
expected: preflight/release succeeds using effective policy
base manifest remains unchanged
```

### `exclude_public`

```text
one canonical record
only source decision = exclude_public
expected:
  excluded=1
  blocked=0
  ready=true
  release emits 0 records
```

### legal-review blocker

```text
decision=needs_human_legal_review
expected:
  blocked=1
  ready=false
```

### multi-source publication basis

```text
record sources:
  A = embedded_public
  B = exclude_public

expected:
  mode=embedded
  publication_basis=["A"]
  B represented metadata-only
  blocked=0
```

### external-ref sanitizer

Input source observation contains:

```text
upstream_expected
projection_notes
raw source-only string
```

Expected public overlay:

```text
none of those forbidden fields appear
input == null
external_ref.source_id exists
external_ref.source_input_hash exists
Gold annotation payload remains structurally valid
```

### duplicate/stale decisions

Fail on:

```text
two decisions for one source
wrong source revision
wrong manifest hash
invalid decision hash
missing maintainer approval
```

### release workflow fixture

Run the exact command shape used in `.github/workflows/release.yml` against a small fixture corpus.

This test is important because the current test suite does not adequately exercise the decision-based v2 publication path.

---

## 14.2 PolyNorm importer tests

Add observed category aliases as fixtures.

Verify:

```text
known alias != unsupported_category
source_category remains original
canonical mapping is deterministic
row accounting exact
```

Add one test for `Hashtag or Mention -> social_handle`.

Add one for `Websites -> url_or_email`.

Do not use generic plural stripping as the only mechanism.

---

## 14.3 Campaign tests

Add tests for:

- campaign snapshot hash is deterministic;
- candidate pool partitions 1000/1000/remainder;
- restarting does not duplicate a packet;
- completed review result is never reissued;
- A/B identities must differ;
- review-check happens only after complete A and B;
- adjudication is not issued early;
- finalization is idempotent;
- retry/deferred cases remain accounted;
- one language packet is not silently mixed with another when language routing is enabled.

---

# 15. Documentation changes

Update documentation so an agent on fresh context does not repeat the run2 failure.

## `AGENTS.md`

Add:

> First-release publication does not require complete ingestion of every upstream source. Canonical corpus completeness, public materialization readiness, and upstream ingestion completeness are separate statuses.

Add:

> Do not attempt to semantically review an entire source corpus in one context. Use campaign packets and fresh reviewer contexts.

Add:

> `exclude_public` is a valid terminal source-publication outcome and is not itself a release failure.

## `templates/reviewer-ab-task.md`

Add:

> Never fill a packet with uniform placeholder semantics. If the reviewer cannot confidently review the packet language or domain, return a structured reviewer-capability blocker and do not write a completed review artifact.

This is better than silently stopping after inspecting hundreds of rows.

The harness can then route that packet to another reviewer.

## `templates/release-publish-task.md`

Replace the legacy `--release-sources` example with `--source-decisions`.

Require:

```text
release-preflight ready
blocked=0
excluded explicitly reported
source decision hash
canonical corpus hash
artifact verification
```

---

# 16. Concrete first-release implementation sequence

The coding agent should execute the work in this order.

## Phase A — freeze and baseline

1. Do not change canonical annotations.
2. Record:
   - current commit
   - canonical record count
   - canonical corpus hash
   - corpus status
   - current source census
3. Regenerate the corpus site only after code changes are complete.
4. Do not touch batch-0030 except to preserve it as unfinished work.

Expected baseline from the supplied run:

```text
canonical = 19789
review_gaps = 0
batch-0030 = awaiting_review
batch-0030 cases = 280
```

## Phase B — repair the publication model

Implement P0.2–P0.6:

1. effective in-memory source policy
2. explicit `excluded` publication mode
3. sanitized external source references
4. decision-file-driven release path
5. consistent preflight/release behavior
6. release template/workflow alignment

Do not add more source data in this phase.

## Phase C — build source decision artifact

Create source-policy review/evidence for only the sources needed to classify current canonical records.

Every source should end in one of:

```text
embedded_public
external_ref_only
exclude_public
needs_human_legal_review
```

For the actual first release, no record may remain blocked.

If a source is still legally uncertain, prefer:

```text
exclude_public
```

for `v0.1.0-exp` rather than delaying the entire release.

The source can be added in a later release.

## Phase D — release preflight

Run:

```bash
spokenform-gold validate data/corpus/

spokenform-gold release-preflight \
  --data data/corpus/ \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/reports/v0.1.0-exp-preflight.json
```

Required:

```text
validation_errors = 0
audit.errors = 0
blocked = 0
accounted = canonical_records
ready = true
```

`excluded` may be non-zero.

## Phase E — build local immutable release

```bash
spokenform-gold release \
  --version 0.1.0-exp \
  --data data/corpus/ \
  --controls data/controls \
  --maturity experimental \
  --coverage-profile all-active \
  --conflict-adjudication release/conflict-adjudication.json \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/releases/spokenform-gold-v0.1.0-exp
```

Then verify:

```text
manifest
checksums
corpus loader
records browser
source materialization census
oracle audit
coverage
controls
release notes
```

## Phase F — benchmark smoke test

Load the produced release through the normal benchmark adapter.

Do not modify Gold to make Spokenform pass.

A benchmark failure becomes a Spokenform bug/policy investigation.

## Phase G — explicit maintainer authorization

Only after presenting:

```text
version
commit
canonical corpus hash
public record count
embedded count
external-ref count
excluded count
source decision hash
preflight ready=true
release artifact path
checksum verification
```

should the release workflow create the GitHub tag/assets.

---

# 17. After `v0.1.0-exp`: PolyNorm completion campaign

Only after the first release is published:

1. fix PolyNorm category aliases;
2. rerun full 4,300-row ingestion;
3. confirm row accounting;
4. produce a source completeness report;
5. freeze the unseen candidate snapshot;
6. create a PolyNorm campaign;
7. split into deterministic logical batches;
8. route language-homogeneous review packets;
9. run independent A/B in fresh contexts;
10. run anomaly checks;
11. adjudicate;
12. finalize accepted rows;
13. send unresolved cases to retry pool;
14. regenerate corpus site;
15. release as a later benchmark version.

This campaign can run over many agent invocations without requiring the human to inspect JSONL.

---

# 18. Definition of done for the coding agent

The first-release task is done only when all of the following are true:

- [ ] Canonical corpus remains valid.
- [ ] Canonical corpus record count/hash are recorded.
- [ ] `release/source-release-decisions.json` exists.
- [ ] All source decisions validate against one base manifest snapshot.
- [ ] `exclude_public` produces exclusions, not blockers.
- [ ] `needs_human_legal_review` still blocks.
- [ ] Source decisions work without mutating the base manifest.
- [ ] Public external-ref objects do not contain `upstream_expected` or other restricted source text.
- [ ] Release preflight reports `blocked=0`.
- [ ] Preflight accounts for every canonical record as embedded, external-ref, excluded, or blocked.
- [ ] Release artifact builds through the same command path as CI.
- [ ] Release manifest reports excluded records explicitly.
- [ ] Release checksums verify.
- [ ] Release browser opens and record IDs work.
- [ ] Existing corpus site is regenerated from the frozen canonical snapshot.
- [ ] Release notes clearly state that full PolyNorm ingestion is incomplete.
- [ ] Batch-0030 remains separate unless it has independently completed A/B + adjudication + finalization.
- [ ] Full test suite, Ruff, formatting, and `make check` pass in the real repository.
- [ ] No publication/tagging happens without explicit maintainer authorization.

---

# 19. Non-goals for `v0.1.0-exp`

Do **not** do these before the first release:

- do not review all missing 2,220 PolyNorm rows;
- do not force batch-0030 through with a weak reviewer;
- do not mark all difficult cases `no_change`;
- do not lower validation rules;
- do not silently embed PolyNorm source text;
- do not claim complete PolyNorm coverage;
- do not resolve source licensing through an LLM semantic row review;
- do not rebuild the entire corpus merely to obtain modern lineage for every historical row;
- do not require 100% upstream-source ingestion for an experimental benchmark release;
- do not edit Gold to match current Spokenform predictions.

---

# 20. Recommended end state

After this implementation, project status should look conceptually like:

```text
Canonical corpus
  records: 19,789
  valid: yes
  usable locally: yes
  first-release snapshot: frozen

Public v0.1.0-exp
  source-policy decisions: complete for publication classification
  blocked records: 0
  embedded records: N
  external-ref records: M
  deliberately excluded records: K
  N + M + K = 19,789
  artifact verified: yes

PolyNorm source campaign
  upstream: 4,300
  official IDs already represented: 2,080
  unseen official IDs: 2,220
  current batch-0030: 280 awaiting review
  mapping exclusions to repair: 1,940
  first-release blocker: no
  post-release data-growth task: yes
```

That is the important project correction:

> **Ship the benchmark snapshot first. Improve upstream completeness iteratively afterward.**

The current repository has already done the difficult work of building a sizable
canonical corpus, stable IDs, validation, HTML inspection, review machinery,
source accounting, and release infrastructure. The missing step is to make the
publication boundary explicit and mechanically correct instead of treating every
incomplete upstream source as a reason not to release.
