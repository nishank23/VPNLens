-- Missing: one query combining those results. API, dashboard, and VPN ingestion remain empty placeholders.
-- Your next exercise: write sql/ip_lookup.sql.
-- 1. Accept one IPv4 address and one ASN source filename.
-- 2. Return ip, country_code, city_name, prefix, origin_group, and snapshot_at.
-- 3. Keep every origin group tied to the most specific prefix.
-- 4. Preserve the input IP when either dataset has no match; return NULL for missing fields.
-- Hint: use an input CTE, separate matching CTEs, then LEFT JOIN. Geolocation uses numeric range containment; ASN uses CIDR containment.
-- Check normal matches, tied origins, and missing matches. Compare results against the existing separate lookups.
-- After this works, inspect query performance, then add ASN-to-organization enrichment.
-- Try the SQL first; paste your attempt for review.


-- SELECT
--     country_code,
--     city_name
--     FROM ip2location
-- WHERE ip_range @> ('8.8.8.8'::inet - '0.0.0.0'::inet);




WITH input AS (
    SELECT
        %(ip_address)s::inet AS ip,
        %(source_file)s::text AS source_file
),

ASNORDER AS(
SELECT
    prefix,
    origin_group,
    snapshot_at,
    DENSE_RANK() OVER (ORDER BY masklen(prefix) DESC ) as specificity_rank
FROM asn_prefix_origins
WHERE source_file = %(source_file)s
AND %(ip_address)s::inet <<= prefix
),

ASN_MEMBERS AS (
    SELECT
        prefix,
        origin_group,
        snapshot_at,
        unnest(string_to_array(origin_group, ',')) AS asn
    FROM ASNORDER
    WHERE specificity_rank = 1
),
ORG_ASN AS (
    SELECT prefix,
        origin_group,
        asn,
        m.snapshot_at AS snapshot_at,
        a.snapshot_at AS org_snapshot_at,
        a.source_file AS org_source_file,
        a.aut_name,
        a.org_id
    FROM ASN_MEMBERS m
    LEFT JOIN raw_asn_mappings a
    ON asn = a.aut
    AND a.source_file = %(org_source_file)s::text
),
ASN_OWNERS AS(
    SELECT r.prefix,
    r.origin_group, r.snapshot_at,

    jsonb_agg(
        jsonb_build_object(
            'asn', r.asn,
            'org_name', o.org_name,
            'org_country_code', o.country,
            'org_snapshot_at', r.org_snapshot_at,
            'org_source_file', r.org_source_file
        )
        ORDER BY r.asn::bigint
    ) AS asn_owners
    from ORG_ASN r
    LEFT JOIN raw_org_mappings o
        ON r.org_id = o.org_id
    AND r.org_source_file = o.source_file
    GROUP BY r.prefix, r.origin_group, r.snapshot_at)

SELECT i.ip,
    ip2.country_code,
    ip2.city_name,
    a.prefix,
    a.origin_group,
    a.snapshot_at,
    COALESCE(a.asn_owners, '[]'::jsonb) AS asn_owners
FROM input i
LEFT JOIN ip2location ip2
    ON ip2.ip_range @> (i.ip - '0.0.0.0'::inet)
LEFT JOIN ASN_OWNERS a
    ON i.ip <<= a.prefix;





-- SELECT *
-- FROM ASN_MEMBERS;




-- SELECT ip,ip2.country_code,ip2.city_name, prefix, origin_group, snapshot_at
-- FROM input i
-- LEFT JOIN ip2location ip2
-- ON ip2.ip_range @> (i.ip - '0.0.0.0'::inet)
-- LEFT JOIN ASNORDER A
-- on i.ip <<= A.prefix
-- AND A.specificity_rank = 1
-- ;
