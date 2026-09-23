-- ============================================
-- VPN Lens - Database Schema
-- ============================================

DROP TABLE IF EXISTS ip2location;
DROP TABLE IF EXISTS raw_ip2location;


-- ============================================
-- Raw IP2Location data
-- ============================================

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


-- ============================================
-- Clean IP2Location data
-- ============================================

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
    time_zone VARCHAR(8),
    ip_range INT8RANGE NOT NULL
);


-- ============================================
-- Index for IP range lookups
-- ============================================

CREATE INDEX IF NOT EXISTS idx_ip2location_ip_range
ON ip2location
USING GIST (ip_range);
