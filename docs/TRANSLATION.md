# Translation and locale-transplant policy

Translation is a candidate-generation stage before the sentence-centric v2 Gold workflow. It never creates canonical Gold directly.

## Roles

Each production batch uses independent translator A and translator B artifacts, followed by a separate translation adjudicator. The resulting fixed target sentence then enters the ordinary semantic reviewer A/B and Gold adjudicator stages.

Translator artifacts must preserve the source record ID and oracle hash, use truthful stable translator IDs, and never contain current Spokenform output, the other translator's work, or semantic Gold decisions. A and B may disagree on target wording. The translation-check gate verifies structure and independence, not linguistic quality.

## Transfer modes

- `semantic_translation` preserves a natural written phenomenon in the target locale.
- `locale_transplant` preserves benchmark intent while adapting locale conventions such as dates, currency, units, counters, addresses, and time expressions.
- `not_transferable` is a valid translator or adjudicator outcome for language-specific or source-specific phenomena.

The translation adjudicator may select A, select B, write a complete merged solution, exclude the case, or mark it unresolved. A merged solution is a new complete target proposal, not a concatenation.

## Licensing

Only repository-owned curated expressions or explicitly approved sources with adaptation and redistribution permission may seed translated candidates. PolyNorm `CC-BY-NC-ND-4.0`, metadata-only sources, unknown licenses, and external-reference-only records are blocked. PolyNorm Japanese and Chinese data remain external evidence and are never translated or embedded by this workflow.

Translation candidates use the repository-owned `spokenform_translation` source identity and retain `translation_parent_record_id`, `translation_parent_oracle_hash`, target locale, transfer relation, and parent family suggestion. Detailed model prompts and private transcripts belong under the configured work root, not canonical JSONL.

## Identity and coverage

The legacy NFKC sentence identity remains unchanged so existing record IDs remain permanent. Collection and census report compatibility-character collisions before they can be silently grouped. A future identity policy version must be evaluated against all existing IDs before migration.

Japanese uses `ja` / `ja-JP`, Korean uses `ko` / `ko-KR`, and Mandarin Chinese uses `zh` / `zh-CN`. Traditional Chinese locales are separate targets. Translation-derived and native provenance are reported separately under the experimental CJK coverage profile; stable release language targets are unchanged.

## Operational sequence

```text
translation-prepare -> translation-packet -> translation-merge ->
translation-check -> translation-adjudication-packet ->
translation-adjudication-merge -> translation-finalize ->
collect -> semantic review A/B -> review-check -> adjudicate -> batch-finalize -> validate
```
