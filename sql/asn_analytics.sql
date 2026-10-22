-- Hint: use POSITION('_' IN origin_as_raw) > 0 to detect an underscore. With LIKE, _ has a special wildcard meaning.

SELECT COUNT(*) FILTER(WHERE POSITION('_' IN origin_as_raw) > 0) as multi_origin_rows,
        COUNT(*) FILTER(WHERE POSITION(',' IN origin_as_raw) > 0) as as_set_rows

 FROM raw_asn_prefixes
WHERE source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz';


SELECT prefix_address,prefix_length, origin_as_raw
FROM raw_asn_prefixes
WHERE source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz'
AND (
    POSITION('_' IN origin_as_raw) > 0 AND POSITION(',' IN origin_as_raw) > 0
);

SELECT origin_as_raw, string_to_array(origin_as_raw, '_') as origin_groups
FROM raw_asn_prefixes
WHERE source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz'
AND (
    POSITION('_' IN origin_as_raw) > 0 AND POSITION(',' IN origin_as_raw) > 0
);


    SELECT origin_as_raw,unnest(string_to_array(origin_as_raw, '_')) as origin_groups
    FROM raw_asn_prefixes
    WHERE source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz'
    AND (
        POSITION('_' IN origin_as_raw) > 0 AND POSITION(',' IN origin_as_raw) > 0
    );

-- Transformation preview. LIMIT applies to expanded output rows.
SELECT
    (prefix_address || '/' || prefix_length::text)::cidr AS prefix,
    unnest(string_to_array(origin_as_raw, '_')) AS origin_group,
    source_file,
    snapshot_at,
    ingested_at
FROM raw_asn_prefixes
LIMIT 10;

-- Full transformation preview; this may return over a million rows.
SELECT
    (prefix_address || '/' || prefix_length::text)::cidr AS prefix,
    unnest(string_to_array(origin_as_raw, '_')) AS origin_group,
    source_file,
    snapshot_at,
    ingested_at
FROM raw_asn_prefixes;


-- prefix lookup.
WITH matching_prefixes AS (SELECT
    prefix,
    origin_group,
    masklen(prefix) as prefix_length,
    DENSE_RANK() OVER(
    ORDER BY masklen(prefix) DESC
    ) AS specificity_rank

FROM asn_prefix_origins
WHERE snapshot_at = '2026-10-01 12:00:00+00'
AND '185.186.206.1'::inet <<= prefix
  AND source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz'
)

SELECT prefix, origin_group, prefix_length
FROM matching_prefixes
WHERE specificity_rank = 1
ORDER BY prefix, origin_group;
