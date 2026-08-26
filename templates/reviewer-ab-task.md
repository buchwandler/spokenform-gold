# Independent Reviewer A/B, Sentence-Centric v2

Run this template in two distinct fresh contexts, once for slot A and once for
slot B. Replace placeholders with truthful values.

## Isolation

You are reviewer `<A_OR_B>` for batch `<BATCH_ID>`, using stable identity
`<REVIEWER_ID>`. Read the relevant annotation policy, taxonomy, schema, and your
assigned blind packet only. Do not inspect source observations, upstream
expectations, current Spokenform output, the other review, adjudication files,
or the full corpus.

A 1,000-case logical batch may require multiple bounded packet invocations.
Packet inputs contain blind-review fields only. The complete artifact must still
cover the entire logical batch.

## Packet and output

Create or consume packets with deterministic limits on both cases and serialized
UTF-8 bytes. Never overwrite the blind artifact. Merge packet results into:

```text
<a.complete.jsonl>
<b.complete.jsonl>
```

Use the packet merge command so preserved blind fields, one reviewer identity,
atomic output, idempotence, and conflicting duplicate detection are enforced.

Each completed row preserves `review_schema_version: "2.0.0"`, `case_id`,
`reviewer_slot`, language, locale, input, and family ID. Add the truthful
reviewer ID, a complete annotation, and the slot-specific completion status.

## Independent semantic review

For every case determine spans, categories, machine-readable semantics,
ambiguity, policy, canonical and accepted unit variants, rejected variants,
canonical full-sentence output, and false-positive risk. Do not invent missing
context. For `no_change`, expected output equals input, units are empty, and
`negative_for` is non-empty.

Keep canonical output in accepted outputs and keep accepted and rejected outputs
disjoint. Preserve the meaning of the input rather than matching an upstream
answer or current implementation output.

## Mechanical handoff

Verify valid JSONL, exact case-ID coverage, preserved blind fields, one stable
truthful reviewer identity, assigned slot, complete annotations, and no hidden
source or implementation fields. Then run the single-review validation and the
aggregate gate:

```bash
spokenform-gold validate-review <COMPLETE> --slot <A_OR_B> --contract v2
spokenform-gold review-check --batch <BATCH_ROOT> \
  --review-a <A_COMPLETE> --review-b <B_COMPLETE>
```

Do not enumerate the JSONL to the human. Report only batch, slot, identity,
paths, counts, ambiguity/no-change counts, flagged cases, and check results.
