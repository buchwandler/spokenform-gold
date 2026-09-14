# Gold Release Publication

Use this role only after v2 integration has produced an immutable local release
artifact. Publication requires explicit user authorization for the exact version
and commit.

## Authoring and export boundary

The authoring source is the `data/corpus/` directory, with one language shard per `data/corpus/<language>.jsonl`. A family-safe split layout, when a
consumer requires it, is a generated export artifact. It is not editable
canonical Gold state. Do not alter annotations, provenance, taxonomy, policy, or
family assignments during publication.

## Verify locally

```bash
git status --short
git rev-parse HEAD
make check
spokenform-gold validate data/corpus/
spokenform-gold release-preflight --data data/corpus/ \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/reports/release-preflight.json
spokenform-gold release --version <VERSION> --data data/corpus/ \
  --controls data/controls --maturity experimental \
  --coverage-profile all-active \
  --conflict-adjudication release/conflict-adjudication.json \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/releases/<VERSION>
```

Preflight must report `ready=true`, `blocked=0`, and `accounted=canonical_records`. Deliberately excluded records are reported explicitly and do not block an experimental release.

Inspect the manifest, checksums, records report, coverage, controls, source
lock, and taxonomy/schema snapshots. Record version, commit, manifest hash,
record/family/language counts, validation result, and unresolved blockers.

## Authorization and publication

Do not tag, push, or publish until the user authorizes this exact artifact.
Present the version, commit, manifest hash, gate results, local path, and
Spokenform integration result first. After authorization, publish through the
repository release workflow and independently verify tag, assets, checksums,
manifest, and report. A publication failure requires a new reviewed version.

A Spokenform benchmark failure is an implementation or policy investigation,
not a reason to rewrite Gold.
