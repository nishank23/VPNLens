SELECT s.source_id, s.indicator_type, s.provider, s.source_url,
       s.content_sha256, s.fetched_at, s.checked_at,
       s.checked_at < CURRENT_TIMESTAMP - INTERVAL '48 hours' AS stale
FROM ip_evidence e
JOIN ip_evidence_snapshots s ON s.snapshot_id = e.snapshot_id AND s.active
WHERE e.ip = %(ip_address)s::inet
ORDER BY s.indicator_type, s.source_id;
