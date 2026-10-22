-- DROP TABLE IF EXISTS raw_asn_prefixes;
CREATE TABLE raw_asn_prefixes(
    prefix_address TEXT NOT NULL,
    prefix_length INT NOT NULL,
    origin_as_raw TEXT NOT NULL,
    source_file TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT * FROM raw_asn_prefixes LIMIT 10;
BEGIN;
CREATE TABLE asn_prefix_origins(
    prefix CIDR NOT NULL,
    origin_group TEXT NOT NULL,
    source_file TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL ,
    ingested_at TIMESTAMPTZ NOT NULL ,
    UNIQUE (source_file, prefix, origin_group)
);

COMMIT;
