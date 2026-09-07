# First experimental release source-policy authorization

The maintainer authorized publication decisions for all sources currently represented by the frozen canonical corpus in the coding-agent session on 2026-09-07:

> I authorize all sources which are now included.

The decision set uses the existing source manifest materialization boundary. Repository-owned sources are `embedded_public`. Upstream sources are `external_ref_only`, so public release overlays contain provenance references and hashes but do not embed upstream source text.

This authorization applies to the experimental local release only. It does not authorize a Git tag, remote push, public publication, or completion of missing upstream ingestion.
