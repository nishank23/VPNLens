SELECT evidence_v2_sources_public() AS result FROM (SELECT %(payload)s::jsonb) AS input;
