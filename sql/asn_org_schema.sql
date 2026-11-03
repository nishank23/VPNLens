-- aut, changed, aut_name, org_id, opaque_id, source
-- raw asn_mappings

CREATE TABLE raw_asn_mappings(
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

CREATE TABLE raw_org_mappings(
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
