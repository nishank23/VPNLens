-- Total raw records

SELECT COUNT(*) AS total_rows
FROM raw_ip2location;


-- IP range validation

SELECT
    MIN(ip_from) AS min_ip_from,
    MAX(ip_to) AS max_ip_to
FROM raw_ip2location;


SELECT COUNT(*) AS invalid_ranges
FROM raw_ip2location
WHERE ip_from > ip_to;


SELECT COUNT(*) AS missing_boundaries
FROM raw_ip2location
WHERE ip_from is NULL OR ip_to is NULL;


SELECT COUNT(*) AS out_of_ipv4_domain
FROM raw_ip2location
WHERE ip_from < 0 OR ip_from > 4294967295 OR ip_to < 0 OR
ip_to > 4294967295;



SELECT ip_from, ip_to , COUNT(*) as occurrences
FROM raw_ip2location
GROUP BY ip_from, ip_to
HAVING COUNT(*) > 1 
LIMIT 10;

-- Country distribution

SELECT
    country_code,
    COUNT(*) AS records
FROM raw_ip2location
GROUP BY country_code
ORDER BY records DESC
LIMIT 15;


-- Placeholder values

SELECT
    COUNT(*) FILTER (WHERE country_code = '-') AS dash_country,
    COUNT(*) FILTER (WHERE country_name = '-') AS dash_country_name,
    COUNT(*) FILTER (WHERE region_name = '-') AS dash_region,
    COUNT(*) FILTER (WHERE city_name = '-') AS dash_city,
    COUNT(*) FILTER (WHERE zip_code = '-') AS dash_zip,
    COUNT(*) FILTER (WHERE time_zone = '-') AS dash_timezone
FROM raw_ip2location;


-- Duplicate ranges

SELECT COUNT(*) AS duplicate_ranges_groups
FROM (
    SELECT ip_from, ip_to
    FROM raw_ip2location
    GROUP BY ip_from, ip_to
    HAVING COUNT(*) > 1
) duplicates;

SELECT
    current_database() AS database_name,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;

SELECT COUNT(*) AS remaining_placeholder_rows
FROM ip2location
WHERE country_name = '-'
   OR country_code = '-'
   OR time_zone = '-'
   OR zip_code = '-'
   OR city_name = '-'
   OR region_name = '-';

SELECT ip_from , ip_to , ip_range, ip_range @> ip_from as contains_start,
ip_range @> ip_to as contains_end from ip2location LIMIT 5;

SELECT COUNT(*) AS invalid_endpoint_rows from ip2location
WHERE NOT(ip_range @> ip_from) OR NOT(ip_range @> ip_to);

SELECT COUNT(*) as overextended_range_rows 
FROM ip2location WHERE
ip_range @> (ip_from-1) OR ip_range @> (ip_to+1);

EXPLAIN (ANALYZE, BUFFERS) SELECT country_code , country_name , city_name FROM ip2location 
WHERE ip_range @>755603456::bigint;

SELECT ip_from , ip_to from ip2location ORDER BY ip_from , ip_to 
LIMIT 10;

WITH range_check AS (SELECT ip_from , MAX(ip_to) OVER(
	order by ip_from , ip_to
	ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
) as max_previous_ip_to
from ip2location
)
SELECT COUNT(*) as gap_count
FROM range_check WHERE 
ip_from > (max_previous_ip_to + 1);

WITH range_check AS (SELECT ip_from , MAX(ip_to) OVER(
	order by ip_from , ip_to
	ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
) as max_previous_ip_to
from ip2location
)
SELECT COUNT(*) as overlapping_rows
FROM range_check
WHERE ip_from <= max_previous_ip_to;


SELECT MIN(ip_from) as first_ip , MAX(ip_to) as last_ip FROM
ip2location;
   