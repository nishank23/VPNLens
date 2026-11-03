-- Non-destructive bootstrap of the existing reviewed model.
-- ============================================
-- VPN Lens - Database Schema
-- ============================================


-- ============================================
-- Raw IP2Location data
-- ============================================

CREATE TABLE IF NOT EXISTS raw_ip2location (
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

CREATE TABLE IF NOT EXISTS ip2location (
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

-- DROP TABLE IF EXISTS raw_asn_prefixes;
CREATE TABLE IF NOT EXISTS raw_asn_prefixes(
    prefix_address TEXT NOT NULL,
    prefix_length INT NOT NULL,
    origin_as_raw TEXT NOT NULL,
    source_file TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS asn_prefix_origins(
    prefix CIDR NOT NULL,
    origin_group TEXT NOT NULL,
    source_file TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL ,
    UNIQUE (source_file, prefix, origin_group)
);

CREATE INDEX IF NOT EXISTS idx_asn_prefix_origins_prefix
ON asn_prefix_origins
USING GIST (prefix inet_ops);

-- aut, changed, aut_name, org_id, opaque_id, source
-- raw asn_mappings

CREATE TABLE IF NOT EXISTS raw_asn_mappings(
    aut TEXT NOT NULL,
    changed TEXT,
    aut_name TEXT NOT NULL,
    org_id TEXT NOT NULL,
    opaque_id TEXT NOT NULL,
    source TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT NOT NULL,
    UNIQUE (source_file, aut)


);



-- org_id, changed, org_name, country, source
-- raw org mapping

CREATE TABLE IF NOT EXISTS raw_org_mappings(
    org_id TEXT NOT NULL,
    changed TEXT,
    org_name TEXT NOT NULL,
    country TEXT NOT NULL,
    source TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT NOT NULL,
    UNIQUE (source_file, org_id)

);

CREATE TABLE IF NOT EXISTS ip_evidence_snapshots (
    snapshot_id UUID PRIMARY KEY,
    source_id TEXT NOT NULL,
    indicator_type TEXT NOT NULL CHECK (indicator_type IN ('vpn_server', 'tor_exit')),
    provider TEXT,
    source_url TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    fetched_at TIMESTAMPTZ NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    ipv4_count BIGINT NOT NULL CHECK (ipv4_count > 0),
    ipv6_skipped BIGINT NOT NULL CHECK (ipv6_skipped >= 0),
    active BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (source_id, content_sha256)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ip_evidence_active_source
    ON ip_evidence_snapshots (source_id) WHERE active;
CREATE TABLE IF NOT EXISTS ip_evidence (
    snapshot_id UUID NOT NULL REFERENCES ip_evidence_snapshots(snapshot_id),
    ip INET NOT NULL CHECK (family(ip) = 4 AND masklen(ip) = 32),
    PRIMARY KEY (snapshot_id, ip)
);
CREATE INDEX IF NOT EXISTS idx_ip_evidence_ip ON ip_evidence (ip);

CREATE INDEX IF NOT EXISTS idx_asn_prefix_origins_snapshot
ON asn_prefix_origins (snapshot_at DESC, source_file DESC);
CREATE INDEX IF NOT EXISTS idx_raw_asn_mappings_snapshot
ON raw_asn_mappings (snapshot_at DESC, source_file DESC);
