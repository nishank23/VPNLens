-- Read-only validation and profiling queries.
-- Expected results are documented for the current complete IPv4 snapshot.
-- These queries report results; they do not automatically reject bad data.
-- Check that tables are populated: many error counts also return 0 on empty tables.

-- 1. Raw data validation and profiling

-- Expected: a nonzero count. Current snapshot: 2,996,298 rows.
-- Future source snapshots may legitimately have a different row count.
SELECT COUNT(*) AS total_rows
FROM raw_ip2location;

-- Expected for full IPv4 coverage: 0 and 4294967295.
-- These extremes alone do not prove the absence of internal gaps.
SELECT
    MIN(ip_from) AS min_ip_from,
    MAX(ip_to) AS max_ip_to
FROM raw_ip2location;

-- Expected: 0. The start of a range must not exceed its end.
SELECT COUNT(*) AS invalid_ranges
FROM raw_ip2location
WHERE ip_from > ip_to;

-- Expected: 0. Either missing boundary makes a source range incomplete.
SELECT COUNT(*) AS missing_boundaries
FROM raw_ip2location
WHERE ip_from IS NULL OR ip_to IS NULL;

-- Expected: 0. BIGINT permits numbers outside the IPv4 domain.
SELECT COUNT(*) AS out_of_ipv4_domain
FROM raw_ip2location
WHERE ip_from < 0
   OR ip_from > 4294967295
   OR ip_to < 0
   OR ip_to > 4294967295;

-- Expected: 0. Counts repeated boundary-pair groups, not excess rows.
SELECT COUNT(*) AS duplicate_range_groups
FROM (
    SELECT ip_from, ip_to
    FROM raw_ip2location
    GROUP BY ip_from, ip_to
    HAVING COUNT(*) > 1
) AS duplicates;

-- Profile: number of source ranges per country, not individual IP addresses.
-- No fixed expected distribution.
SELECT
    country_code,
    COUNT(*) AS records
FROM raw_ip2location
GROUP BY country_code
ORDER BY records DESC
LIMIT 15;

-- Profile: source placeholders are allowed in raw data; counts need not be 0.
SELECT
    COUNT(*) FILTER (WHERE country_code = '-') AS dash_country,
    COUNT(*) FILTER (WHERE country_name = '-') AS dash_country_name,
    COUNT(*) FILTER (WHERE region_name = '-') AS dash_region,
    COUNT(*) FILTER (WHERE city_name = '-') AS dash_city,
    COUNT(*) FILTER (WHERE zip_code = '-') AS dash_zip,
    COUNT(*) FILTER (WHERE time_zone = '-') AS dash_timezone
FROM raw_ip2location;

-- 2. Clean data validation

-- Expected: equal, nonzero counts and row_counts_match = true.
-- Equality also passes when both tables are empty; inspect the counts too.
-- Equal counts alone do not prove that all transformed values are correct.
SELECT
    (SELECT COUNT(*) FROM raw_ip2location) AS raw_rows,
    (SELECT COUNT(*) FROM ip2location) AS clean_rows,
    (SELECT COUNT(*) FROM raw_ip2location)
        = (SELECT COUNT(*) FROM ip2location) AS row_counts_match;

-- Expected: 0. Source '-' placeholders should become NULL in clean data.
SELECT COUNT(*) AS remaining_placeholder_rows
FROM ip2location
WHERE country_name = '-'
   OR country_code = '-'
   OR time_zone = '-'
   OR zip_code = '-'
   OR city_name = '-'
   OR region_name = '-';

-- Expected: 0. Each stored range must contain both inclusive source endpoints.
-- Relies on the clean schema's NOT NULL constraints for boundaries and ip_range.
SELECT COUNT(*) AS invalid_endpoint_rows
FROM ip2location
WHERE NOT (ip_range @> ip_from)
   OR NOT (ip_range @> ip_to);

-- Expected: 0. Neither address immediately outside a source range belongs in it.
SELECT COUNT(*) AS overextended_range_rows
FROM ip2location
WHERE ip_range @> (ip_from - 1)
   OR ip_range @> (ip_to + 1);

-- Expected for this complete snapshot: 0 internal gaps.
-- Counts gaps between ranges, not the number of uncovered addresses.
WITH range_check AS (
    SELECT
        ip_from,
        MAX(ip_to) OVER (
            ORDER BY ip_from, ip_to
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS max_previous_ip_to
    FROM ip2location
)
SELECT COUNT(*) AS gap_count
FROM range_check
WHERE ip_from > (max_previous_ip_to + 1);

-- Expected: 0 rows overlapping at least one earlier range.
-- Inclusive endpoints mean equality is an overlap. This does not count pairs.
-- Repeat the CTE because its scope ends at the preceding statement's semicolon.
WITH range_check AS (
    SELECT
        ip_from,
        MAX(ip_to) OVER (
            ORDER BY ip_from, ip_to
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS max_previous_ip_to
    FROM ip2location
)
SELECT COUNT(*) AS overlapping_rows
FROM range_check
WHERE ip_from <= max_previous_ip_to;

-- Expected: 0 and 4294967295. Use together with the internal-gap check.
-- Numeric coverage does not imply every address has a known location.
SELECT
    MIN(ip_from) AS first_ip,
    MAX(ip_to) AS last_ip
FROM ip2location;

-- 3. Exploratory queries and diagnostics

-- Identify the database connection used to run these checks.
SELECT
    current_database() AS database_name,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;

-- Sample duplicate groups for investigation. Expected: no rows in this snapshot.
SELECT
    ip_from,
    ip_to,
    COUNT(*) AS occurrences
FROM raw_ip2location
GROUP BY ip_from, ip_to
HAVING COUNT(*) > 1
LIMIT 10;

-- Preview only: both containment flags should be true.
-- The full-table endpoint check above provides broader validation.
SELECT
    ip_from,
    ip_to,
    ip_range,
    ip_range @> ip_from AS contains_start,
    ip_range @> ip_to AS contains_end
FROM ip2location
LIMIT 5;

-- Preview the first ten ranges in boundary order.
SELECT ip_from, ip_to
FROM ip2location
ORDER BY ip_from, ip_to
LIMIT 10;

-- ANALYZE executes this read-only lookup and reports its actual performance.
-- Inspect index usage and buffer activity; timings vary between executions.
EXPLAIN (ANALYZE, BUFFERS)
SELECT country_code, country_name, city_name
FROM ip2location
WHERE ip_range @> 755603456::bigint;




