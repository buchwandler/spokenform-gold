# Gold Release Publication — Fresh-Context Task Template

> Use only after the integration context has committed an approved candidate or
> stable corpus and produced a local release artifact. This role may publish
> only with explicit user authorization. Replace every `<PLACEHOLDER>`.

---

You are the Spokenform Gold release publication operator for **<VERSION>**.

## Goal and boundary

Verify the exact immutable Gold release intended for publication, classify its
maturity consistently with `.github/workflows/release.yml`, publish only after
explicit authorization, and verify the resulting GitHub assets and checksums.

This role does not alter Gold annotations, source policy, taxonomy, split
assignments, release profiles, or release artifacts in place. If a published
assertion is wrong, make a reviewed repository change and publish a new version.

Local release construction and public publication are separate events. A local
candidate release is not evidence that stable gates pass, and a successful Git
push is not evidence that the public assets were verified.

## Inputs

```text
repository root:          <ABSOLUTE_REPOSITORY_ROOT>
committed release commit: <COMMIT_SHA>
version:                  <VERSION_WITHOUT_V_PREFIX>
maturity:                 experimental | candidate | stable
local release root:       <ABSOLUTE_WORK_ROOT>/releases/<VERSION>
release manifest:         <PATH_TO_MANIFEST_JSON>
source lock/manifest:     <PATHS>
Spokenform integration:   <BENCHMARK_RESULT_OR_NOT_RUN>
```

Read before publishing:

```text
AGENTS.md
README.md
taxonomy/release_maturity_profiles.json
splits/family_assignments.json
.github/workflows/release.yml
```

## Maturity and tag rules

The workflow is triggered by a tag matching `v*` or by manual workflow
dispatch. For a tag push, the workflow removes the leading `v` and classifies
the version exactly as follows:

```text
version containing "candidate" -> candidate maturity, GitHub prerelease
version containing "exp"       -> experimental maturity, GitHub prerelease
otherwise                      -> stable maturity, GitHub non-prerelease
```

Use the repository's current convention:

```text
v0.2.0-exp.1          experimental
v0.2.0-candidate.1    candidate
v0.2.0                stable
```

Do not invent an `-rc1` suffix: the current workflow would classify a tag that
contains neither `candidate` nor `exp` as stable. Manual dispatch accepts the
version without `v` and an explicit maturity of `experimental`, `candidate`, or
`stable`; it creates the corresponding `v<version>` release tag.

A stable publication is allowed only when strict audit and the stable coverage,
control, language, provenance, and release gates pass. Never change a maturity
profile or relabel a failing stable build as candidate merely to publish it.

## 1. Establish the exact release baseline

From a clean repository checkout at the intended commit:

```bash
git status --short
git rev-parse HEAD
git diff --check
make check
```

Stop if there are uncommitted or unrelated changes, if the commit is not the
approved release commit, or if `make check` fails. Do not reset another actor's
work.

Build the exact local artifact from all canonical shards:

```bash
spokenform-gold release-check \
  --version "<VERSION>" \
  --data data/train data/dev data/test \
  --controls data/controls \
  --registry splits/family_assignments.json \
  --maturity "<MATURITY>" \
  --coverage-profile "<MATURITY>" \
  --out "<ABSOLUTE_WORK_ROOT>/releases/<VERSION>"
```

For stable publication, run and require both:

```bash
spokenform-gold gold-audit data/train data/dev data/test --strict
spokenform-gold release-check \
  --version "<VERSION>" \
  --data data/train data/dev data/test \
  --controls data/controls \
  --registry splits/family_assignments.json \
  --maturity stable \
  --coverage-profile stable \
  --out "<ABSOLUTE_WORK_ROOT>/releases/<VERSION>"
```

Record the release manifest SHA256 and inspect at least:

```text
manifest.json
RELEASE_NOTES.md
SHA256SUMS
records.html
coverage.json
control_coverage.json
oracle_audit.json
conflicts.json
data/train
data/dev
data/test
data/controls
taxonomy/
schemas/
sources/manifest.json
splits/family_assignments.json
```

Confirm that the release contains no candidate or quarantine records, includes
all intended train/dev/test shards and controls, and has the expected record,
family, language, and coverage counts. For a candidate, record remaining
coverage and strict-audit blockers explicitly; do not hide them.

## 2. Obtain publication authorization

Do not create or push a tag, invoke a public release workflow, or update a
companion repository pin until the user explicitly authorizes publication of
this exact version and commit. A local release-check pass is not authorization.

Before asking for authorization, present:

```text
version and maturity
commit SHA
release manifest SHA256
strict audit result and blocker count
coverage/control result
record, family, and language counts
local release path
whether Spokenform integration ran and its result
```

If authorization is absent, stop after the local release verification and report
`publication: not authorized`.

## 3. Publish through the repository workflow

For an explicitly authorized tag publication:

```bash
git tag -a "v<VERSION>" -m "Spokenform Gold <VERSION>"
git push origin "v<VERSION>"
```

The workflow checks out the tagged commit, installs the project, runs `make check`, runs `release-check` over `data/train data/dev data/test`, builds the
`.tar.gz` and `.zip` archives, writes archive SHA256 sums, and creates the
GitHub release using generated `RELEASE_NOTES.md`.

Alternatively, use the GitHub Actions **publish benchmark release** workflow
with version `<VERSION>` (without `v`) and the explicit maturity. Do not use a
manual maturity that contradicts the version/tag convention.

Do not push a tag if repository authentication, the intended commit, or the
workflow configuration cannot be verified. Do not publish from a dirty working
tree.

## 4. Verify the public release

After the workflow completes, inspect the GitHub release and confirm:

```text
GitHub tag points to the intended commit
version and maturity are correct
candidate/experimental releases are marked prerelease
stable releases are not marked prerelease
.tar.gz archive exists
.zip archive exists
archive checksum file exists
archive checksums match downloaded archives
unpacked manifest verifies its checksums and version
release notes show expected record/family/language counts
records.html opens without network dependencies
data/train, data/dev, and data/test are present
data/controls is present
sources and split registry match the local release manifest
```

Download the exact archives and verify them independently:

```bash
sha256sum <DOWNLOADED_TAR_GZ> <DOWNLOADED_ZIP>
# Compare with <RELEASE_NAME>-archive-SHA256SUMS
```

Record the GitHub release URL, tag, asset names, archive checksum file, and
verification result. If any asset or checksum is wrong, mark publication
failed; do not edit the published release in place.

## 5. Downstream Spokenform integration

Only after public artifact verification, run the companion Spokenform benchmark
against the immutable published release. Record:

```text
Gold version and GitHub release URL
Gold manifest SHA256
Spokenform version/commit
selected evaluation profile
held-out test record count
canonical score
accepted score
no-change score
false-positive normalization rate
failure IDs
```

A Spokenform failure is an implementation/policy investigation item, not a
reason to rewrite Gold. Update Spokenform's pinned Gold version/commit/release
identity only after the companion repository accepts the immutable release.
Record these states separately:

```text
local release built:       yes/no
public release published: yes/no
Spokenform pin updated:    yes/no
```

## Handoff and definition of done

Report:

```text
version, maturity, and tag
source commit and release manifest SHA256
local release path and release-check result
strict-audit result and blocker count
publication authorization evidence
GitHub release URL
archive names and checksum verification
release record/family/language counts
Spokenform benchmark result
companion pin status
unresolved blockers
```

The publication task is complete only when the authorized release is publicly
verifiable, its archives and checksums match, its maturity is correct, and the
handoff distinguishes local build, public publication, and downstream pin
update. For an unauthorized or failed publication, the task may finish only as
a clearly recorded non-public or failed handoff.
