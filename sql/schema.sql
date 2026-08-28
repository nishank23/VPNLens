DROP TABLE IF EXISTS raw_ip2location,ip2location;

CREATE TABLE raw_ip2location (
    ip_from BIGINT,
    ip_to BIGINT,
    country_code CHAR(2),
    country_name VARCHAR(64),
    region_name VARCHAR(128),
    city_name VARCHAR(128),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    zip_code VARCHAR(30),
    time_zone VARCHAR(8)
);


CREATE TABLE ip2location (
    ip_from BIGINT NOT NULL,
    ip_to BIGINT NOT NULL,
    country_code CHAR(2),
    country_name VARCHAR(64),
    region_name VARCHAR(128),
    city_name VARCHAR(128),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    zip_code VARCHAR(30),
    time_zone VARCHAR(8)
);

COPY raw_ip2location (
    ip_from,
    ip_to,
    country_code,
    country_name,
    region_name,
    city_name,
    latitude,
    longitude,
    zip_code,
    time_zone
)
FROM '/Users/nishankbansal/Documents/VPNLens/data/IP2LOCATION-LITE-DB11.CSV'
WITH (
    FORMAT csv,
    HEADER false,
    QUOTE '"'
);


SELECT COUNT(*) AS total_rows
FROM raw_ip2location;


SELECT
    MIN(ip_from) AS min_ip_from,
    MAX(ip_to) AS max_ip_to
FROM raw_ip2location;


SELECT COUNT(*) AS invalid_ranges
FROM raw_ip2location
WHERE ip_from > ip_to;



SELECT
    country_code,
    COUNT(*) AS records
FROM raw_ip2location
GROUP BY country_code
ORDER BY records DESC
LIMIT 15;


--Checking for Null values if we have any

SELECT
    COUNT(*) FILTER (WHERE country_code IS NULL) AS null_country,
    COUNT(*) FILTER (WHERE country_name IS NULL) AS null_country_name,
    COUNT(*) FILTER (WHERE latitude IS NULL) AS null_latitude,
    COUNT(*) FILTER (WHERE longitude IS NULL) AS null_longitude,
    COUNT(*) FILTER (WHERE zip_code IS NULL) AS null_zip,
    COUNT(*) FILTER (WHERE time_zone IS NULL) AS null_timezone
FROM raw_ip2location;


--Checking for - Values if we have any

SELECT
    COUNT(*) FILTER (WHERE country_code = '-') AS dash_country,
    COUNT(*) FILTER (WHERE country_name = '-') AS dash_country_name,
    COUNT(*) FILTER (WHERE region_name = '-') AS dash_region,
    COUNT(*) FILTER (WHERE city_name = '-') AS dash_city,
    COUNT(*) FILTER (WHERE zip_code = '-') AS dash_zip,
    COUNT(*) FILTER (WHERE time_zone = '-') AS dash_timezone
FROM raw_ip2location;



SELECT
    MIN(latitude) AS min_latitude,
    MAX(latitude) AS max_latitude,
    MIN(longitude) AS min_longitude,
    MAX(longitude) AS max_longitude
FROM raw_ip2location;


SELECT
    ip_from,
    ip_to,
    COUNT(*) AS duplicate_count
FROM raw_ip2location
GROUP BY ip_from, ip_to
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 20;


SELECT COUNT(*) AS duplicate_ranges
FROM (
    SELECT ip_from, ip_to
    FROM raw_ip2location
    GROUP BY ip_from, ip_to
    HAVING COUNT(*) > 1
) duplicates;


SELECT COUNT(*) AS null_or_placeholder_records
FROM raw_ip2location
WHERE country_code = '-'
   OR country_name = '-'
   OR region_name = '-'
   OR city_name = '-'
   OR zip_code = '-'
   OR time_zone = '-';


INSERT INTO ip2location (
    ip_from,
    ip_to,
    country_code,
    country_name,
    region_name,
    city_name,
    latitude,
    longitude,
    zip_code,
    time_zone
)
SELECT
    ip_from,
    ip_to,
    NULLIF(country_code, '-'),
    NULLIF(country_name, '-'),
    NULLIF(region_name, '-'),
    NULLIF(city_name, '-'),
    latitude,
    longitude,
    NULLIF(zip_code, '-'),
    NULLIF(time_zone, '-')
FROM raw_ip2location;



SELECT COUNT(*) AS clean_rows
FROM ip2location;



SELECT
    COUNT(*) FILTER (WHERE country_code = '-') AS dash_country,
    COUNT(*) FILTER (WHERE country_name = '-') AS dash_country_name,
    COUNT(*) FILTER (WHERE region_name = '-') AS dash_region,
    COUNT(*) FILTER (WHERE city_name = '-') AS dash_city,
    COUNT(*) FILTER (WHERE zip_code = '-') AS dash_zip,
    COUNT(*) FILTER (WHERE time_zone = '-') AS dash_timezone
FROM ip2location;



SELECT
    COUNT(*) FILTER (WHERE country_code IS NULL) AS null_country,
    COUNT(*) FILTER (WHERE country_name IS NULL) AS null_country_name,
    COUNT(*) FILTER (WHERE region_name IS NULL) AS null_region,
    COUNT(*) FILTER (WHERE city_name IS NULL) AS null_city
FROM ip2location;

ALTER TABLE ip2location
ADD COLUMN ip_range int8range;

UPDATE ip2location
SET ip_range = int8range(ip_from, ip_to, '[]');

SELECT
    ip_from,
    ip_to,
    ip_range,
    country_code,
    country_name,
    city_name
FROM ip2location
LIMIT 10;


