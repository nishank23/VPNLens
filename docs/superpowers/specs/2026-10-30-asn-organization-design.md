# ASN organization enrichment: proposed design

Date: 2026-10-30

Status updated 2026-10-31: the user supplied and corrected the raw table model
and authorized proceeding. The Python loader and tests are implemented. The
October snapshot is loaded in the project database. The user implemented the
standalone ownership query; its read-only runner and seven checks now pass.
The user completed combined-output integration on 2026-11-01, choosing nested
member arrays and separate routing/organization provenance. The Python runner
now supplies all three parameters; API implementation is subsequent work. See
[loader instructions and verification](../../asn-organizations.md).

## Intent and scope

Add CAIDA AS-to-Organization as the third logical dataset in VPNLens. It supplies
AS names, inferred organization ownership, and organization country. Organization
country remains separate from the IP geolocation country already returned by
IP2Location.

The user chose owner enrichment before VPN/proxy classification. The completed
geolocation/routing lookup remains the baseline. VPN detection, additional
providers, an API, a frontend, and scheduled refreshes are subsequent work.

## Approaches considered

- Owner enrichment first: selected by the user. It connects existing routing
  origins to human-readable network and organization information.
- VPN/proxy evidence first: deferred. It adds a different type of evidence and
  requires selecting a separate feed and its coverage.

For this selected source, a pinned local bulk snapshot is proposed because the
existing pipelines and lookup operate on PostgreSQL snapshots. A live ownership
API would add network dependencies and a separate freshness policy to each
lookup. This bulk-loading choice is a proposal for user review, not an
architecture decision already made by the user.

## Verified source contract

Official documentation:
<https://www.caida.org/catalog/datasets/as-organizations/>

Format reference and downloads:
<https://publicdata.caida.org/datasets/as-organizations/>

Proposed initial snapshot:
<https://publicdata.caida.org/datasets/as-organizations/20261001.as-org2info.txt.gz>

The dated snapshot, rather than the moving `latest` filename, was inspected on
2026-10-30. The source was read in memory only; no dataset was saved in the
repository and no project database was accessed.

- Compressed size: 4,024,948 bytes.
- SHA-256: `e010e11531e097d02cef583f666f578e7723ec5db58b1c8cb43d4c8e6f416c0d`.
- Organization records: 98,447.
- ASN records: 122,668.
- Duplicate identifiers within either record type: none observed.

The gzip contains two pipe-delimited sections identified by format comments:

```text
# format:org_id|changed|org_name|country|source
# format:aut|changed|aut_name|org_id|opaque_id|source
```

`aut` is the ASN. The ASN record references an organization through `org_id`.
`source` identifies the originating registry; it is not the downloaded filename.
`changed` is the WHOIS record's change date; it is not the snapshot date.

Both record types have valid blank metadata. In the inspected snapshot:

- 33,740 organization change dates and 40,390 ASN change dates were empty.
- 4,798 organization names and 14,623 AS names were empty.
- 44,742 ASN opaque identifiers were empty.

Do not infer a date or name when the source omits it. The user will decide the
storage types and missing-value handling while designing the tables.

## Ownership and first implementation slice

The user owns the table model, keys, snapshot relationships, core SQL,
failure-handling decisions, and final review. Codex implements routine Python,
CLI/configuration, logging, automated checks, and documentation against the
reviewed contract.

The first slice loads both record types from one explicitly selected local
snapshot and proves an ASN-to-organization lookup. The user will first sketch:

1. Storage for each record type, including columns and data types.
2. Primary or unique keys, including how identifiers are scoped to a snapshot.
3. How ASN rows refer to organization rows without mixing snapshots.
4. Separate registry-source, source-file, snapshot-date, and ingestion metadata.

No complete DDL or enrichment SQL is supplied here, so the user can attempt the
model first. Existing raw/clean conventions should be considered rather than
automatically introducing another storage pattern.

Proposed Python responsibilities after that review:

- Read an explicit local gzip path; expose the input path through a CLI.
- Recognize both format markers and parse their documented field counts.
- Preserve raw values according to the reviewed table contract.
- Use the existing psycopg and standard-library dependencies.
- Load through COPY, report per-section counts and source identity, and test
  the reviewed replacement and failure behavior in a disposable database.

## Failure behavior to review with the model

The existing pipelines use transactional snapshot replacement. The proposed
extension replaces both record types for the selected snapshot in one
transaction and preserves other snapshots. A failed load would leave the prior
committed snapshot intact.

Before implementing the loader, the user must decide how empty sections,
malformed records, duplicate identifiers, and unresolved organization references
should affect that transaction. Empty optional source metadata is a different
case from structurally malformed records; the verified source contains many
legitimate blanks.

## Acceptance criteria

1. Both documented record types load from the selected file with matching
   parsed/stored counts. The counts above are observations for this file, not
   constants for future snapshots.
2. Required source, snapshot, and ingestion metadata remain traceable.
3. Repeating a load and encountering a failed load follow the user-reviewed
   replacement and transaction policy; other snapshots remain intact.
4. A fixture ASN resolves to its organization using the selected snapshot.
   Missing mappings remain visible as missing information.
5. Real-data spot checks, once loaded, agree with the inspected snapshot:
   ASN 15169 belongs to Google LLC (US); ASN 28885 belongs to Oman
   Telecommunications Company (S.A.O.G) (OM); ASN 206350 belongs to
   Oman Research and education Network (OMREN) (OM).
6. Existing geolocation/routing lookup tests continue to pass.

## Integration after the first slice

The user will extend the core lookup after the source model and ingestion are
verified. The existing comma-separated `origin_group`, such as `28885,206350`,
must remain intact as routing evidence. Its members need individual ownership
lookups; casting that entire string to one ASN would be invalid.

Before changing the combined output, agree whether member details are nested
under each origin group or returned through a separate result shape. Do not
silently multiply or collapse the existing routing rows. Select organization
and routing snapshots explicitly, and expose their dates separately.

## Validation and stop condition

Use standard-library parser tests and disposable PostgreSQL integration tests
for the reviewed source contract. Do not run write tests against the normal
project database. Report fixture proof separately from full-snapshot load and
lookup evidence.

The first slice ends when the source loads correctly and the selected-snapshot
ASN-to-organization lookup passes its checks. Then review the combined-query
integration with the user. Do not add an API or frontend inside this slice.

Preserve CAIDA attribution in project documentation. Downloaded source data
remains under the existing ignored `data/` directory when the actual ingestion
work begins. No GitHub push is authorized by this design.
