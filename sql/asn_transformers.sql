-- Executed by transform_asn_prefixes.py inside its transaction.
-- The runner supplies source_file as a named psycopg parameter.
INSERT INTO asn_prefix_origins (
    prefix,
    origin_group,
    source_file,
    snapshot_at,
    ingested_at
)
SELECT
    (prefix_address || '/' || prefix_length::text)::cidr AS prefix,
    unnest(string_to_array(origin_as_raw, '_')) AS origin_group,
    source_file,
    snapshot_at,
    ingested_at
FROM raw_asn_prefixes
WHERE source_file = %(source_file)s;
