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
