---
goal: "Implement the first-release finalization brief so the frozen canonical corpus has a policy-correct experimental release path and the post-release PolyNorm campaign is resumable and auditable."
files:
  - "@spokenform_gold/release.py"
  - "@spokenform_gold/source_policy.py"
  - "@spokenform_gold/source_resolver.py"
  - "@spokenform_gold/source_manifest.py"
  - "@spokenform_gold/campaign.py"
  - "@spokenform_gold/cli.py"
  - "@spokenform_gold/importers/polynorm.py"
  - "@taxonomy/mappings/polynorm.json"
  - "@release/source-release-decisions.json"
  - "@tests/test_release.py"
  - "@tests/test_source_policy.py"
  - "@tests/test_campaign.py"
  - "@tests/test_importers.py"
  - "@tests/test_importer_expansion.py"
  - "@templates/release-publish-task.md"
  - "@templates/reviewer-ab-task.md"
  - "@README.md"
  - "@AGENTS.md"
  - "@.github/workflows/release.yml"
  - "@docs"
test_commands:
  - "python -m pytest -q"
  - "ruff check ."
  - "ruff format --check ."
  - "make check"
expected_outputs:
  - "All focused release, source-policy, importer, campaign, browser, and documentation tests pass."
  - "The decision-based experimental release preflight accounts for every canonical record with zero blocked records."
  - "The generated release passes checksum and browser verification without mutating sources/manifest.json."
  - "The full test suite, Ruff, formatting, and make check exit 0."
acceptance_criteria:
  - id: ac-0001
    text: "The frozen canonical corpus remains unchanged semantically, validates successfully, and its record count and canonical corpus hash are recorded in release artifacts and status documentation."
    mandatory: true
  - id: ac-0002
    text: "release/source-release-decisions.json exists as an auditable schema-valid input, contains one valid authorized decision per currently included source, and all decisions bind to one base source-manifest revision and hash."
    mandatory: true
  - id: ac-0003
    text: "An effective in-memory source manifest validates decisions for duplicates, stale revisions, stale manifest hashes, malformed decision hashes, and missing approval, while leaving the checked-in base manifest unchanged."
    mandatory: true
  - id: ac-0004
    text: "Publication planning supports embedded, external_ref, excluded, and blocked modes, treats exclude_public as an intentional non-blocking exclusion, selects a valid multi-source publication basis, and leaves needs_human_legal_review unresolved as a blocker."
    mandatory: true
  - id: ac-0005
    text: "Preflight and release use the same effective source policy, report embedded/external_ref/excluded/blocked counts and public totals, account for every canonical record, and allow excluded records while requiring blocked=0 and validation/audit success."
    mandatory: true
  - id: ac-0006
    text: "External-reference overlays are built from an explicit public-source whitelist and contain no upstream_expected, original_text, normalized_text, expected, input, raw source payload, or other restricted source-derived text while preserving a valid annotation and source input hash."
    mandatory: true
  - id: ac-0007
    text: "The decision-based release CLI, workflow, templates, README, and agent guidance are consistent, and the exact CI command shape succeeds against a small fixture release."
    mandatory: true
  - id: ac-0008
    text: "The PolyNorm importer preserves original source categories and maps every documented observed alias explicitly, including Hashtag or Mention to social_handle and Websites to url_or_email, without fuzzy plural normalization."
    mandatory: true
  - id: ac-0009
    text: "PolyNorm import diagnostics retain exact row accounting and classify remaining failures by their actual mechanical reason rather than unsupported_category for known aliases."
    mandatory: true
  - id: ac-0010
    text: "Campaign creation freezes a deterministic candidate/source snapshot with hashes and accounting, fills deterministic non-overwriting logical batches, routes bounded language-aware packets, and exposes campaign-next and campaign-merge for reviewer A, reviewer B, and adjudicator results."
    mandatory: true
  - id: ac-0011
    text: "Campaign merge and progression are idempotent and safe: completed results are not reissued, reviewer A/B identities remain distinct, review-check and adjudication are gated by complete prior artifacts, retry/deferred cases remain accounted, and anomaly detection flags suspicious uniform reviews for fresh re-review without changing Gold."
    mandatory: true
  - id: ac-0012
    text: "Campaign completion reports every upstream row in an explicit terminal/current bucket with unaccounted=0, and finalization remains idempotent without silently promoting unresolved cases."
    mandatory: true
  - id: ac-0013
    text: "Release artifacts include the required manifest fields, publication plan, source census, oracle/audit and coverage reports, review-evidence summary, taxonomy/schema snapshots, release notes describing incomplete PolyNorm ingestion, records browser, and verified SHA256SUMS."
    mandatory: true
  - id: ac-0014
    text: "The corpus browser and release artifacts expose the canonical corpus hash consistently, distinguish canonical completeness from upstream ingestion completeness, and preserve batch-0030 as unfinished work."
    mandatory: true
  - id: ac-0015
    text: "No Git tag or remote publication is performed; the local experimental release is built and verified, and final validation evidence is recorded."
    mandatory: true
todos:
  - id: todo-0001
    text: "Record the frozen baseline for data/corpus/, including commit, record count, canonical corpus hash, corpus status, source census, and batch-0030 state, without editing canonical annotations or batch-0030."
    mandatory: true
    validation_hint: "Use bounded status/count/hash commands and verify git diff contains no corpus or batch-0030 changes."
  - id: todo-0002
    text: "Implement source-decision validation and effective in-memory source policy in spokenform_gold/source_policy.py and related manifest helpers, including atomic apply-all support if useful, duplicate/stale/approval checks, and decision artifact generation/loading."
    mandatory: true
    validation_hint: "Run focused source-policy tests covering valid decisions, duplicate sources, stale revision/hash, invalid decision hash, and missing approval."
  - id: todo-0003
    text: "Update release planning and materialization in spokenform_gold/release.py and spokenform_gold/source_resolver.py for excluded records, multi-source bases, shared effective policy, sanitized external references, preflight metrics, review-evidence metrics, publication_plan.json, and complete experimental release manifests/notes."
    mandatory: true
    validation_hint: "Run focused release tests and build a small decision-based v2 fixture release, then verify manifest, browser, checksums, and unchanged base source manifest."
  - id: todo-0004
    text: "Create release/source-release-decisions.json for every source currently represented by the frozen canonical corpus using the user's authorization and the source manifest's current materialization policy, with auditable evidence and approval metadata, and ensure the checked-in artifact validates against the one base manifest snapshot."
    mandatory: true
    validation_hint: "Run source decision validation and release-preflight against data/corpus; confirm no represented source is missing or blocked."
  - id: todo-0005
    text: "Repair the PolyNorm importer and taxonomy mapping with explicit aliases and social_handle/url_or_email mappings while preserving source_category and exact row accounting."
    mandatory: true
    validation_hint: "Run importer and importer-expansion tests with fixtures for every documented alias family and verify no known alias remains unsupported_category."
  - id: todo-0006
    text: "Extend spokenform_gold/campaign.py and the CLI with frozen source snapshots, campaign-create/fill, deterministic batch partitioning, language routing and packet limits, campaign-next/campaign-merge for all roles, retry/accounting state, and campaign completion/finalization behavior."
    mandatory: true
    validation_hint: "Run campaign tests for deterministic hashes, 1000/1000/remainder partitioning, idempotence, role gates, distinct A/B identities, language routing, retry accounting, and finalization."
  - id: todo-0007
    text: "Add deterministic review anomaly detection and capability-blocker handling to the review/campaign workflow, producing reports and requiring fresh review without automatically changing annotations."
    mandatory: true
    validation_hint: "Run anomaly tests for uniform statuses/rationales, no-change normalization packets, empty units, repeated oracle objects, and clean heterogeneous reviews."
  - id: todo-0008
    text: "Unify canonical corpus hash reporting between corpus site and release/status outputs, regenerate the frozen corpus site, and add the required source/review/publication census and release identity fields."
    mandatory: true
    validation_hint: "Run corpus-site and release identity tests and verify canonical_corpus_hash is shared while site_content_hash remains separately reported."
  - id: todo-0009
    text: "Align .github/workflows/release.yml, templates/release-publish-task.md, templates/reviewer-ab-task.md, README.md, AGENTS.md, and relevant docs with decision-based experimental publication, explicit exclusions, bounded fresh review campaigns, and incomplete PolyNorm disclosure."
    mandatory: true
    validation_hint: "Run documentation contract tests and inspect the exact workflow command arguments for source decisions, experimental maturity, all-active coverage, and artifact verification."
  - id: todo-0010
    text: "Add or update release/source-policy, importer, campaign, anomaly, workflow-fixture, browser-hash, and artifact tests required by the brief, including the exact CI release command shape."
    mandatory: true
    validation_hint: "Run all focused tests before marking this todo complete."
  - id: todo-0011
    text: "Build and verify the local v0.1.0-exp release from the frozen canonical corpus, including preflight, release browser, corpus loader, source census, oracle audit, coverage, controls, release notes, manifest, and checksum verification, without tagging or publishing."
    mandatory: true
    validation_hint: "Run validate, release-preflight, release, checksum verification, and benchmark adapter smoke checks; record paths and compact gate results."
  - id: todo-0012
    text: "Run the complete validation suite, resolve implementation failures without weakening validation, record all implementation changes and evidence, and confirm the final git diff preserves the frozen corpus and unfinished batch-0030."
    mandatory: true
    validation_hint: "Run python -m pytest -q, ruff check ., ruff format --check ., and make check; inspect git status and release verification output."
---

# First-release finalization and PolyNorm campaign plan

## Summary

Implement the full `01_todo.md` brief while preserving the current canonical Gold corpus and keeping batch-0030 unfinished. The primary release work makes source-policy decisions authoritative at release-build time without mutating the base manifest, treats deliberate public exclusions as a valid outcome, sanitizes external references, and produces a verified experimental local release. The post-release work adds explicit PolyNorm alias handling and a resumable, bounded, language-aware campaign harness with anomaly detection and complete row accounting.

## Implementation Changes

- Capture the frozen baseline and make the authorized source decision artifact explicit for all sources represented by the current corpus.
- Add effective source-policy derivation, strict decision validation, excluded publication planning, multi-source basis selection, release accounting, and decision-driven materialization.
- Replace deep-copy external overlays with a public provenance whitelist and preserve source input hashes for hydration.
- Repair PolyNorm category aliases and add regression fixtures without changing source provenance labels.
- Expand campaign orchestration from existing batch discovery to frozen candidate snapshots, deterministic filling, bounded packet routing, merge/progression gates, retries, anomaly reports, and completion accounting.
- Unify corpus hash identity and emit the release census, review-evidence summary, publication plan, browser, notes, and checksum artifacts required by the brief.
- Align documentation and CI examples with the modern decision-based experimental release path.

## Tests

- Focused source-policy and release tests cover all publication modes, effective policy, stale/duplicate/invalid decisions, legal blockers, multi-source bases, overlay sanitization, artifact fields, and the exact workflow command shape.
- Importer tests cover each observed PolyNorm alias family, source-category preservation, social handles, websites, span resolution, and exact row accounting.
- Campaign tests cover deterministic snapshots and partitioning, packet bounds and language routing, idempotent merge/progression, role isolation, review gates, retries, anomalies, completion, and finalization.
- Run `python -m pytest -q`, `ruff check .`, `ruff format --check .`, and `make check` before completion.
- Build and verify the local `v0.1.0-exp` artifact, including preflight, loader/browser checks, source census, audit, coverage, release notes, manifest, and SHA256SUMS.

## Assumptions

- The user's authorization applies to every source currently represented by the frozen canonical corpus. Decisions will follow each represented source's current manifest materialization policy: repository-owned public sources remain embedded-public, and restricted sources use their current approved external-reference policy unless the release model requires deliberate exclusion.
- The chat authorization is recorded in artifact approval metadata as an explicit user authorization, without inventing a personal maintainer identity or legal determination beyond the supplied authorization.
- Experimental release publication is local-only. No GitHub tag, remote push, or public asset publication is authorized by this task.
- The first release may disclose incomplete PolyNorm upstream ingestion and preserve retry/deferred campaign work instead of importing or reviewing missing rows before release.

## Out of Scope

- Changing canonical annotations to match Spokenform or upstream expectations.
- Semantically reviewing the missing PolyNorm rows or forcing batch-0030 through review.
- Publishing or tagging the release.
- Lowering validation, oracle, source provenance, family-safety, or negative-control requirements.
