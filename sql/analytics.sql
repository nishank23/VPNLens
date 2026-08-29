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

SELECT COUNT(*) AS duplicate_ranges
FROM (
    SELECT ip_from, ip_to
    FROM raw_ip2location
    GROUP BY ip_from, ip_to
    HAVING COUNT(*) > 1
) duplicates;