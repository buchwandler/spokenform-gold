# Licensing Policy

This document explains how licensing is applied within the
`buchwandler/spokenform-gold` repository.

It is a repository policy and scope statement. It does not modify the text or
terms of either the Apache License 2.0 or the Creative Commons Attribution 4.0
International license.

## Summary

Spokenform Gold uses separate licenses for software and original benchmark
material:

| Material                                                          | License                                                            |
| ----------------------------------------------------------------- | ------------------------------------------------------------------ |
| Software, CLI, importers, validators, scorers, scripts, and tests | Apache License 2.0                                                 |
| Original Spokenform Gold benchmark data                           | Creative Commons Attribution 4.0 International                     |
| Original Spokenform Gold taxonomy and structured annotation data  | Creative Commons Attribution 4.0 International                     |
| Third-party benchmark material                                    | The applicable upstream license; not relicensed by this repository |
| Third-party code                                                  | The applicable upstream license; not relicensed by this repository |

The complete Apache License 2.0 text is in `LICENSE`.

The complete Creative Commons Attribution 4.0 International legal text is in
`LICENSE-DATA`.

Official references:

- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

## 1. Software license: Apache-2.0

Unless a file explicitly states otherwise, original software authored for
Spokenform Gold is licensed under the Apache License, Version 2.0.

This includes, in particular:

```text
src/
tests/
scripts/
tools/
```

and other source-code files, command-line tooling, benchmark validators,
importers, scorers, report generators, and build/test automation created for
this repository.

The SPDX identifier is:

```text
Apache-2.0
```

A source file may optionally include:

```text
SPDX-License-Identifier: Apache-2.0
```

The full license terms are in `LICENSE`.

## 2. Original benchmark data license: CC BY 4.0

Unless a file, directory, record, source manifest, or provenance field states
otherwise, **original benchmark data created specifically for the Spokenform
Gold project** is licensed under the Creative Commons Attribution 4.0
International license.

This generally includes original material under directories such as:

```text
data/dev/
data/test/
data/challenge/
data/judge_gold/
```

but only to the extent that the material is original to Spokenform Gold and the
repository's copyright holders have the authority to license it.

It also generally includes original structured benchmark metadata and taxonomy
material under:

```text
taxonomy/
```

where that material was created for Spokenform Gold.

The SPDX identifier is:

```text
CC-BY-4.0
```

The full license terms are in `LICENSE-DATA`.

## 3. Requested attribution for Spokenform Gold data

When redistributing, publishing, adapting, or otherwise using original
Spokenform Gold benchmark material under CC BY 4.0, the requested attribution
is:

```text
Spokenform Gold contributors
https://github.com/buchwandler/spokenform-gold
Licensed under CC BY 4.0
```

Where reasonable, also identify the benchmark release or commit used, for
example:

```text
Spokenform Gold v0.1.0
```

or a Git commit hash.

If the material has been modified, indicate that changes were made, as required
by CC BY 4.0.

This attribution request does not imply endorsement by the Spokenform Gold
project or its contributors.

## 4. Third-party datasets are excluded from the CC BY 4.0 grant

The CC BY 4.0 grant in this repository applies only to material for which the
Spokenform Gold copyright holders have the authority to grant that license.

It does **not** automatically apply to material originating from external
benchmarks or other third parties.

Examples include, but are not limited to:

```text
PolyNorm
async-TN
Proteno
```

Third-party examples, annotations, normalized strings, metadata, source files,
or other materials remain subject to their respective upstream licenses,
copyright notices, terms, and attribution requirements.

Importing a third-party record into the Spokenform Gold candidate schema does
not relicense the underlying third-party material.

Do not remove upstream copyright, license, attribution, or provenance
information.

## 5. Imported candidate data

The repository may contain generated candidate records under locations such as:

```text
data/candidates/
```

A candidate record can contain a mixture of:

- original Spokenform Gold metadata;
- source identifiers;
- upstream text;
- upstream normalized text;
- derived annotations;
- automatically inferred fields.

Therefore, do not assume that every field in a candidate record is CC BY 4.0.

The `source` and provenance metadata for the record determine the origin of
third-party components.

Where licensing status is unclear, treat the record as not redistributable
until the upstream terms have been reviewed.

If a source manifest marks a source as `metadata_only`,
`not_redistributable`, or `review_required`, do not ship a public embedded
release that contains the upstream text. Use a source-backed `external_ref`
overlay or keep the source local until policy review is complete.

## 6. Provenance must be preserved

Imported benchmark records should retain enough provenance to determine their
licensing and origin.

Where available, preserve fields such as:

```text
benchmark
source_id
source_version
source_url
source_category
commit
license
license_url
copyright
upstream_expected
source_hash
```

Do not overwrite an upstream expected normalization with a Spokenform Gold
canonical normalization.

Store both when they differ.

## 7. Source manifests

For third-party benchmark integrations, maintain source manifests that record,
where available:

```text
name
version
source URL
commit or revision
license
license URL
copyright notice
retrieval date
source hash
redistribution status
license scope
materialization policy
```

Recommended redistribution-status values include:

```text
allowed
metadata_only
importer_only
review_required
not_redistributable
```

When license terms are uncertain, use:

```text
review_required
```

rather than making an assumption.

The repository uses `materialization_policy` to distinguish sources that may be
embedded in a public release from sources that must remain external or blocked
pending review.

## 8. Documentation

Original project documentation may be distributed under Apache-2.0 unless a
document is explicitly marked CC BY 4.0.

For simplicity, repository maintainers may choose to apply Apache-2.0 to
technical software documentation and CC BY 4.0 to benchmark-policy,
annotation, taxonomy, and dataset documentation.

Where the distinction matters, place an SPDX identifier in the document or
directory metadata.

## 9. Contributions

By contributing material, a contributor must have the right to submit it under
the license applicable to the target portion of the repository.

In particular:

- source-code contributions should be compatible with Apache-2.0;
- original benchmark-data contributions should be licensable under CC BY 4.0;
- third-party benchmark material must retain its original licensing and
  provenance;
- contributors must not submit material that the repository does not have the
  right to redistribute.

A contribution to a CC BY 4.0 data area is understood to be offered under
CC BY 4.0 unless clearly marked otherwise and accepted under a different,
compatible policy.

A contribution to an Apache-2.0 code area is understood to be offered under
Apache-2.0 unless clearly marked otherwise and accepted under a different,
compatible policy.

## 10. Generated and derived benchmark records

Automatically generated data should record its generator and source inputs.

Recommended provenance fields include:

```text
generator
generator_version
template_id
source_record_ids
generation_seed
review_status
```

If generated material incorporates or adapts third-party material, its
redistribution remains subject to applicable upstream rights and license terms.

Do not label derived material as solely CC BY 4.0 unless the repository has the
rights required to do so.

## 11. Machine-learning and benchmark use

CC BY 4.0 permits broad reuse of material covered by that license, including
commercial reuse, subject to its terms and attribution requirements.

This policy does not grant rights in third-party material excluded above.

Users are responsible for determining whether additional laws, contractual
terms, database rights, privacy rules, or third-party rights apply to their
particular use.

## 12. No trademark or endorsement grant

The licenses in this repository do not grant permission to imply that the
Spokenform Gold project, Spokenform, `buchwandler`, or individual contributors
endorse a modified dataset, model, service, benchmark result, or product.

## 13. When adding a new source

Before committing third-party benchmark material:

1. identify the authoritative source;
2. identify its license;
3. determine whether redistribution is permitted;
4. determine attribution requirements;
5. record the source in a manifest;
6. preserve upstream notices;
7. add only the material permitted by the source terms;
8. prefer importer code and metadata when redistribution rights are unclear.

Do not solve a licensing uncertainty by silently copying the dataset into this
repository.

## 14. Precedence

If this policy conflicts with an applicable license text, copyright notice, or
third-party license governing particular material, the applicable legal terms
for that material control.

`LICENSE_POLICY.md` is explanatory and does not replace those legal terms.

## 15. Legal review

This repository policy is intended to make the project's licensing boundaries
explicit and auditable. It is not legal advice.

For material with unclear ownership, unusual database terms, incompatible
licenses, personal data, or significant commercial/legal risk, obtain
appropriate legal review before redistribution.
