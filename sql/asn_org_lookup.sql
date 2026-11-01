WITH ASN_RECORD AS (
    SELECT
        org_id,
        aut,
        aut_name,
        source_file,
        snapshot_at
    FROM raw_asn_mappings
    WHERE aut = %(asn)s::text
    AND source_file = %(source_file)s::text
)






SELECT a.aut,a.aut_name,o.org_name,
    o.country, o.source, a.snapshot_at
FROM ASN_RECORD a
LEFT JOIN raw_org_mappings o
ON a.org_id = o.org_id
AND a.source_file = o.source_file;
