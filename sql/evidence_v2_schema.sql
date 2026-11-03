-- Explicit, additive installation only. Execute in one caller-owned transaction.
CREATE OR REPLACE FUNCTION evidence_v2_public_network(n cidr) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
 SELECT family(n)=4 AND masklen(n)>0 AND NOT EXISTS (
  SELECT FROM unnest(ARRAY['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8',
   '169.254.0.0/16','172.16.0.0/12','192.0.0.0/24','192.0.2.0/24','192.88.99.0/24',
   '192.168.0.0/16','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4']::cidr[]) blocked
  WHERE n && blocked)
$$;

CREATE OR REPLACE FUNCTION evidence_v2_stamp(value text) RETURNS timestamptz
LANGUAGE plpgsql STABLE STRICT AS $$
DECLARE result timestamptz;
BEGIN
 IF value !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN RAISE EXCEPTION 'Timezone required'; END IF;
 result := value::timestamptz;
 IF NOT isfinite(result) OR result > statement_timestamp() THEN RAISE EXCEPTION 'Invalid future timestamp'; END IF;
 RETURN result;
END $$;

-- Match the producer's sorted compact, ASCII JSON digest, including Unicode strings.
CREATE OR REPLACE FUNCTION evidence_v2_canonical(value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE result text; item record; ch text; cp integer; i integer;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'object' THEN
  SELECT '{'||coalesce(string_agg(evidence_v2_canonical(to_jsonb(key))||':'||evidence_v2_canonical(val),',' ORDER BY key COLLATE "C"),'')||'}'
    INTO result FROM jsonb_each(value) AS e(key,val);
 WHEN 'array' THEN
  SELECT '['||coalesce(string_agg(evidence_v2_canonical(val),',' ORDER BY ord),'')||']'
    INTO result FROM jsonb_array_elements(value) WITH ORDINALITY AS e(val,ord);
 WHEN 'string' THEN
  result := '';
  FOR i IN 1..length(value::text) LOOP
   ch := substr(value::text,i,1); cp := ascii(ch);
   IF cp > 65535 THEN
    result := result||'\u'||lpad(to_hex(55296+(cp-65536)/1024),4,'0')||'\u'||lpad(to_hex(56320+(cp-65536)%1024),4,'0');
   ELSIF cp >= 127 THEN result := result||'\u'||lpad(to_hex(cp),4,'0');
   ELSE result := result||ch; END IF;
  END LOOP;
 ELSE result := value::text;
 END CASE;
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION evidence_v2_hash(value jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT encode(sha256(convert_to(evidence_v2_canonical(value),'UTF8')),'hex') $$;

CREATE OR REPLACE FUNCTION evidence_v2_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='evidence_v2_snapshots' AND TG_OP='UPDATE'
    AND to_jsonb(NEW)-'checked_at'=to_jsonb(OLD)-'checked_at'
    AND NEW.checked_at >= OLD.checked_at AND NEW.checked_at <= statement_timestamp() THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Immutable evidence history';
END $$;

CREATE TABLE IF NOT EXISTS evidence_v2_registry (
 registry_sha256 text PRIMARY KEY CHECK(registry_sha256 ~ '^[a-f0-9]{64}$'),
 config jsonb NOT NULL CHECK (jsonb_typeof(config)='object' AND config->>'schema_version'='1' AND jsonb_typeof(config->'sources')='array' AND config ?& ARRAY['schema_version','sources']),
 committed_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 CONSTRAINT evidence_v2_registry_digest CHECK(registry_sha256=evidence_v2_hash(config))
);
CREATE TABLE IF NOT EXISTS evidence_v2_sources (
 registry_sha256 text NOT NULL REFERENCES evidence_v2_registry,
 source_id text NOT NULL CHECK(source_id ~ '^[a-z0-9][a-z0-9-]{0,99}$'),
 enabled boolean NOT NULL,
 config jsonb NOT NULL,
 PRIMARY KEY(registry_sha256,source_id),
 UNIQUE(registry_sha256,source_id,enabled),
 CONSTRAINT evidence_v2_sources_binding CHECK(config->>'source_id'=source_id AND (config->>'enabled')::boolean=enabled),
 CONSTRAINT evidence_v2_sources_config CHECK((
  jsonb_typeof(config)='object' AND config ?& ARRAY['source_id','enabled','family','provider','adapter','basis','role','url','max_bytes','max_age_hours','attribution_url']
  AND jsonb_typeof(config->'source_id')='string' AND jsonb_typeof(config->'family')='string' AND length(btrim(config->>'family'))>0 AND jsonb_typeof(config->'enabled')='boolean' AND jsonb_typeof(config->'max_age_hours')='number' AND jsonb_typeof(config->'max_bytes')='number'
  AND (config->'provider'='null'::jsonb OR (jsonb_typeof(config->'provider')='string' AND length(btrim(config->>'provider'))>0))
  AND config->>'role' IN ('server','exit','unknown') AND config->>'max_age_hours'='48'
  AND config->>'url' ~ '^https://[^/@[:space:]]+([/:][^[:space:]]*)?$'
  AND config->>'attribution_url' ~ '^https://[^/@[:space:]]+([/:][^[:space:]]*)?$'
  AND CASE config->>'adapter'
   WHEN 'host_text' THEN config->>'basis'='provider_list' AND config->>'max_bytes'='5000000'
   WHEN 'cidr_text' THEN config->>'basis'='network_inference' AND config->>'max_bytes'='5000000'
   WHEN 'vpngate_csv' THEN config->>'basis'='provider_list' AND config->>'max_bytes'='25000000'
   WHEN 'dns_a' THEN config->>'basis'='provider_dns' AND config->>'max_bytes'='5000000' AND jsonb_typeof(config->'hosts')='array' AND jsonb_array_length(config->'hosts') BETWEEN 1 AND 100
   ELSE false END) IS TRUE)
);
CREATE TABLE IF NOT EXISTS evidence_v2_snapshots (
 snapshot_id uuid PRIMARY KEY,
 source_id text NOT NULL,
 content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'),
 source_policy_version text NOT NULL,
 source_config jsonb NOT NULL,
 fetched_at timestamptz NOT NULL,
 checked_at timestamptz NOT NULL,
 publisher_at timestamptz,
 ipv4_count bigint NOT NULL CHECK(ipv4_count>=0),
 ipv6_skipped bigint NOT NULL CHECK(ipv6_skipped>=0),
 -- Loading is confined to the creating transaction; committed content cannot grow.
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 UNIQUE(source_id,content_sha256), UNIQUE(snapshot_id,source_id),
 FOREIGN KEY(source_policy_version,source_id) REFERENCES evidence_v2_sources(registry_sha256,source_id),
 CONSTRAINT evidence_v2_snapshots_time CHECK(isfinite(fetched_at) AND isfinite(checked_at) AND fetched_at<=checked_at AND checked_at<=statement_timestamp() AND (publisher_at IS NULL OR (isfinite(publisher_at) AND publisher_at<=checked_at))),
 CONSTRAINT evidence_v2_snapshots_source CHECK(source_config->>'source_id'=source_id)
);
CREATE TABLE IF NOT EXISTS evidence_v2_indicators (
 snapshot_id uuid NOT NULL REFERENCES evidence_v2_snapshots,
 record_key text NOT NULL CHECK(record_key ~ '^[a-f0-9]{64}$'),
 network cidr NOT NULL,
 provider text,
 basis text NOT NULL CHECK(basis IN ('provider_list','provider_dns','network_inference')),
 role text NOT NULL CHECK(role IN ('server','exit','unknown')),
 hostname text,
 method text NOT NULL CHECK(method IN ('host_text','cidr_text','vpngate_csv','dns_a')),
 service_category text NOT NULL CHECK(service_category='vpn'),
 metadata jsonb NOT NULL CHECK(jsonb_typeof(metadata)='object'),
 PRIMARY KEY(snapshot_id,record_key),
 CONSTRAINT evidence_v2_indicators_network_public CHECK(evidence_v2_public_network(network)),
 CONSTRAINT evidence_v2_indicators_identity CHECK(record_key=evidence_v2_hash(jsonb_build_object('network',network::text,'provider',provider,'basis',basis,'role',role,'hostname',hostname,'method',method,'service_category',service_category))),
 CONSTRAINT evidence_v2_indicators_hosts CHECK(method NOT IN ('host_text','dns_a','vpngate_csv') OR masklen(network)=32)
);
CREATE INDEX IF NOT EXISTS evidence_v2_indicators_network_gist ON evidence_v2_indicators USING gist(network inet_ops);
CREATE TABLE IF NOT EXISTS evidence_v2_head (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 registry_sha256 text NOT NULL REFERENCES evidence_v2_registry,
 UNIQUE(singleton,registry_sha256)
);
CREATE TABLE IF NOT EXISTS evidence_v2_active (
 source_id text PRIMARY KEY,
 registry_sha256 text NOT NULL,
 snapshot_id uuid NOT NULL,
 enabled boolean NOT NULL DEFAULT true CHECK(enabled),
 singleton boolean NOT NULL DEFAULT true CHECK(singleton),
 FOREIGN KEY(singleton,registry_sha256) REFERENCES evidence_v2_head(singleton,registry_sha256) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(registry_sha256,source_id,enabled) REFERENCES evidence_v2_sources(registry_sha256,source_id,enabled),
 FOREIGN KEY(snapshot_id,source_id) REFERENCES evidence_v2_snapshots(snapshot_id,source_id)
);
CREATE TABLE IF NOT EXISTS evidence_v2_observations (
 observation_id uuid PRIMARY KEY,
 observation_sha256 text NOT NULL CHECK(observation_sha256 ~ '^[a-f0-9]{64}$'),
 profile_sha256 text NOT NULL CHECK(profile_sha256 ~ '^[a-f0-9]{64}$'),
 network cidr NOT NULL CHECK(masklen(network)=32 AND evidence_v2_public_network(network)),
 observed_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 measurement jsonb NOT NULL,
 UNIQUE(observation_id,observation_sha256),
 CONSTRAINT evidence_v2_observations_time CHECK(isfinite(observed_at) AND observed_at<=statement_timestamp() AND expires_at=observed_at+interval '24 hours'),
 CONSTRAINT evidence_v2_observations_binding CHECK((measurement ?& ARRAY['observation_id','observation_sha256','profile_sha256','source_id','family','record_key','network','provider','basis','role','method','service_category','source_url','content_sha256','observed_at','expires_at','connection_type_claim'] AND measurement->>'observation_id'=observation_id::text AND measurement->>'observation_sha256'=observation_sha256 AND measurement->>'profile_sha256'=profile_sha256 AND (measurement->>'network')::cidr=network AND (measurement->>'observed_at')::timestamptz=observed_at AND (measurement->>'expires_at')::timestamptz=expires_at) IS TRUE),
 CONSTRAINT evidence_v2_observations_metadata CHECK((measurement->>'source_id' ~ '^observation-[a-z0-9][a-z0-9-]{0,99}$' AND measurement->>'family'='measured_exit' AND measurement->>'record_key'=observation_sha256 AND measurement->>'content_sha256'=observation_sha256 AND measurement->>'basis'='exit_observation' AND measurement->>'role'='exit' AND measurement->>'method' IN ('system_tunnel','explicit_http_proxy','browser_import') AND measurement->>'service_category' IN ('vpn','proxy') AND measurement->>'connection_type_claim' IN ('residential','mobile','datacenter','unknown') AND length(measurement->>'provider')>0 AND measurement->>'source_url' ~ '^https://[^/@[:space:]?#]+([/:][^[:space:]?#]*)?$') IS TRUE)
);
CREATE TABLE IF NOT EXISTS evidence_v2_reviews (
 observation_id uuid PRIMARY KEY,
 observation_sha256 text NOT NULL,
 review_state text NOT NULL CHECK(review_state IN ('approved','rejected')),
 reviewed_at timestamptz NOT NULL CHECK(isfinite(reviewed_at) AND reviewed_at<=statement_timestamp()),
 reviewer_sha256 text NOT NULL CHECK(reviewer_sha256 ~ '^[a-f0-9]{64}$'),
 FOREIGN KEY(observation_id,observation_sha256) REFERENCES evidence_v2_observations(observation_id,observation_sha256)
);

CREATE OR REPLACE FUNCTION evidence_v2_bind() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c jsonb; o evidence_v2_observations; snapshot_xid xid8;
BEGIN
 IF TG_TABLE_NAME='evidence_v2_sources' THEN
  IF NOT EXISTS(SELECT FROM evidence_v2_registry r, jsonb_array_elements(r.config->'sources') s WHERE r.registry_sha256=NEW.registry_sha256 AND s=NEW.config) THEN RAISE EXCEPTION 'Source registry mismatch'; END IF;
 ELSIF TG_TABLE_NAME='evidence_v2_snapshots' THEN
  IF TG_OP='INSERT' AND NEW.created_xid IS DISTINCT FROM pg_current_xact_id() THEN RAISE EXCEPTION 'Snapshot creation transaction mismatch'; END IF;
  SELECT config INTO c FROM evidence_v2_sources WHERE registry_sha256=NEW.source_policy_version AND source_id=NEW.source_id;
  IF c IS DISTINCT FROM NEW.source_config OR NOT (c->>'enabled')::boolean THEN RAISE EXCEPTION 'Snapshot source mismatch'; END IF;
 ELSIF TG_TABLE_NAME='evidence_v2_indicators' THEN
  SELECT source_config,created_xid INTO c,snapshot_xid FROM evidence_v2_snapshots WHERE snapshot_id=NEW.snapshot_id;
  IF snapshot_xid IS DISTINCT FROM pg_current_xact_id() THEN RAISE EXCEPTION 'Committed snapshot indicators are immutable'; END IF;
  IF c IS NULL OR NEW.provider IS DISTINCT FROM c->>'provider' OR NEW.basis IS DISTINCT FROM c->>'basis' OR NEW.role IS DISTINCT FROM c->>'role' OR NEW.method IS DISTINCT FROM c->>'adapter' THEN RAISE EXCEPTION 'Indicator source mismatch'; END IF;
 ELSIF TG_TABLE_NAME='evidence_v2_active' THEN
  SELECT source_config-'enabled' INTO c FROM evidence_v2_snapshots WHERE snapshot_id=NEW.snapshot_id;
  IF c IS DISTINCT FROM (SELECT config-'enabled' FROM evidence_v2_sources WHERE registry_sha256=NEW.registry_sha256 AND source_id=NEW.source_id) THEN RAISE EXCEPTION 'Active policy mismatch'; END IF;
 ELSIF TG_TABLE_NAME='evidence_v2_reviews' THEN
  SELECT * INTO o FROM evidence_v2_observations WHERE observation_id=NEW.observation_id;
  IF NEW.reviewed_at < o.observed_at OR (NEW.review_state='approved' AND (NEW.reviewed_at>=o.expires_at OR statement_timestamp()>=o.expires_at)) THEN RAISE EXCEPTION 'Expired or invalid approval'; END IF;
 END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['evidence_v2_registry','evidence_v2_sources','evidence_v2_snapshots','evidence_v2_indicators','evidence_v2_observations','evidence_v2_reviews'] LOOP
  IF NOT EXISTS(SELECT FROM pg_trigger WHERE tgrelid=to_regclass(t) AND tgname='evidence_v2_immutable_history') THEN
   EXECUTE format('CREATE TRIGGER evidence_v2_immutable_history BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION evidence_v2_immutable()',t);
  END IF;
 END LOOP;
 FOREACH t IN ARRAY ARRAY['evidence_v2_sources','evidence_v2_snapshots','evidence_v2_indicators','evidence_v2_active','evidence_v2_reviews'] LOOP
  IF NOT EXISTS(SELECT FROM pg_trigger WHERE tgrelid=to_regclass(t) AND tgname='evidence_v2_bind_source') THEN
   EXECUTE format('CREATE TRIGGER evidence_v2_bind_source BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION evidence_v2_bind()',t);
  END IF;
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION evidence_v2_sources_public() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('sources',coalesce(jsonb_agg(jsonb_build_object(
 'source_id',a.source_id,'indicator_type',CASE s.source_config->>'basis' WHEN 'network_inference' THEN 'network_inference' ELSE 'vpn_server' END,
 'provider',s.source_config->'provider','source_url',s.source_config->>'url','checked_at',s.checked_at,'fetched_at',s.fetched_at,
 'ipv4_count',s.ipv4_count,'ipv6_skipped',s.ipv6_skipped,'stale',s.checked_at+interval '48 hours'<=statement_timestamp(),
 'basis',s.source_config->>'basis','record_kind',CASE s.source_config->>'adapter' WHEN 'cidr_text' THEN 'network' ELSE 'host' END,
 'family',s.source_config->>'family','method',s.source_config->>'adapter') ORDER BY a.source_id),'[]'::jsonb),
 'enabled_source_ids',coalesce(jsonb_agg(a.source_id ORDER BY a.source_id),'[]'::jsonb))
 FROM evidence_v2_active a JOIN evidence_v2_head h USING(registry_sha256) JOIN evidence_v2_snapshots s USING(snapshot_id)
$$;

CREATE OR REPLACE FUNCTION evidence_v2_lookup(payload jsonb) RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE address inet; matches jsonb;
BEGIN
 IF payload->>'ip_address' IS NULL OR payload->>'ip_address' LIKE '%/%' THEN RAISE EXCEPTION 'Expected IPv4 host'; END IF;
 address := (payload->>'ip_address')::inet;
 IF family(address)<>4 OR masklen(address)<>32 THEN RAISE EXCEPTION 'Expected IPv4 host'; END IF;
 SELECT coalesce(jsonb_agg(m ORDER BY m->>'source_id',m->>'record_key'),'[]'::jsonb) INTO matches FROM (
 SELECT jsonb_build_object('source_id',a.source_id,'family',s.source_config->>'family','record_key',i.record_key,'network',i.network::text,
 'provider',i.provider,'basis',i.basis,'role',i.role,'method',i.method,'service_category',i.service_category,
 'source_url',s.source_config->>'url','content_sha256',s.content_sha256,'fetched_at',s.fetched_at,'checked_at',s.checked_at,
 'observed_at',NULL,'expires_at',s.checked_at+interval '48 hours','review_state',NULL,'hostname',i.hostname,
 'metadata',CASE WHEN i.metadata ? 'ttl' THEN jsonb_build_object('ttl',i.metadata->'ttl') ELSE '{}'::jsonb END,
 'connection_type_claim',NULL) m
 FROM evidence_v2_indicators i JOIN evidence_v2_snapshots s USING(snapshot_id)
 JOIN evidence_v2_active a USING(snapshot_id) JOIN evidence_v2_head h ON h.registry_sha256=a.registry_sha256
 WHERE i.network >>= address
 UNION ALL
 SELECT jsonb_build_object('source_id',o.measurement->>'source_id','family','measured_exit','record_key',o.observation_sha256,'network',o.network::text,
 'provider',o.measurement->>'provider','basis','exit_observation','role','exit','method',o.measurement->>'method','service_category',o.measurement->>'service_category',
 'source_url',o.measurement->>'source_url','content_sha256',o.observation_sha256,'fetched_at',o.observed_at,'checked_at',o.observed_at,
 'observed_at',o.observed_at,'expires_at',o.expires_at,'review_state',r.review_state,'hostname',NULL,'metadata','{}'::jsonb,
 'connection_type_claim',o.measurement->>'connection_type_claim')
 FROM evidence_v2_observations o JOIN evidence_v2_reviews r USING(observation_id,observation_sha256)
 WHERE r.review_state='approved' AND o.network >>= address
 ) records;
 RETURN jsonb_build_object('matches',matches);
END $$;

CREATE OR REPLACE FUNCTION evidence_v2_publish(payload jsonb) RETURNS jsonb LANGUAGE plpgsql VOLATILE AS $$
DECLARE reg jsonb:=payload->'registry'; rh text:=payload->>'registry_sha256'; src jsonb; sn jsonb; rec jsonb;
 sid uuid; old evidence_v2_snapshots; changed boolean:=false; enabled_count integer; seen integer:=0;
 fetched timestamptz; checked timestamptz; published timestamptz; existing_records jsonb; previous_active jsonb;
BEGIN
 IF jsonb_typeof(payload->'schema_version') IS DISTINCT FROM 'number' OR payload->>'schema_version' IS DISTINCT FROM '1' OR reg IS NULL OR jsonb_typeof(payload->'snapshots') IS DISTINCT FROM 'array'
 OR jsonb_typeof(reg->'schema_version') IS DISTINCT FROM 'number' OR reg->>'schema_version' IS DISTINCT FROM '1' OR jsonb_typeof(reg->'sources') IS DISTINCT FROM 'array' OR rh IS DISTINCT FROM evidence_v2_hash(reg) THEN RAISE EXCEPTION 'Invalid batch envelope'; END IF;
 IF evidence_v2_stamp(payload->>'checked_at') IS NULL THEN RAISE EXCEPTION 'Missing batch timestamp'; END IF;
 IF NOT EXISTS(SELECT FROM evidence_v2_head WHERE registry_sha256=rh) THEN changed:=true; END IF;
 INSERT INTO evidence_v2_registry(registry_sha256,config) VALUES(rh,reg) ON CONFLICT DO NOTHING;
 FOR src IN SELECT * FROM jsonb_array_elements(reg->'sources') LOOP
  INSERT INTO evidence_v2_sources(registry_sha256,source_id,enabled,config) VALUES(rh,src->>'source_id',(src->>'enabled')::boolean,src) ON CONFLICT DO NOTHING;
 END LOOP;
 IF (SELECT count(*) FROM evidence_v2_sources WHERE registry_sha256=rh)<>jsonb_array_length(reg->'sources') THEN RAISE EXCEPTION 'Duplicate registry source'; END IF;
 SELECT count(*) INTO enabled_count FROM evidence_v2_sources WHERE registry_sha256=rh AND enabled;
 IF enabled_count<>jsonb_array_length(payload->'snapshots') THEN RAISE EXCEPTION 'Incomplete enabled source batch'; END IF;
 SELECT coalesce(jsonb_object_agg(source_id,snapshot_id::text),'{}'::jsonb) INTO previous_active FROM evidence_v2_active;
 DELETE FROM evidence_v2_active;
 INSERT INTO evidence_v2_head(singleton,registry_sha256) VALUES(true,rh) ON CONFLICT(singleton) DO UPDATE SET registry_sha256=excluded.registry_sha256;
 FOR sn IN SELECT * FROM jsonb_array_elements(payload->'snapshots') LOOP
  src:=sn->'source';
  IF NOT EXISTS(SELECT FROM evidence_v2_sources WHERE registry_sha256=rh AND source_id=src->>'source_id' AND enabled AND config=src) THEN RAISE EXCEPTION 'Snapshot not bound to enabled registry'; END IF;
  IF jsonb_typeof(sn->'records') IS DISTINCT FROM 'array' OR (jsonb_array_length(sn->'records')=0 AND src->>'adapter'<>'dns_a') THEN RAISE EXCEPTION 'Invalid empty source'; END IF;
  fetched:=evidence_v2_stamp(sn->>'fetched_at'); checked:=evidence_v2_stamp(sn->>'checked_at'); published:=evidence_v2_stamp(sn->>'publisher_at');
  IF checked IS NULL OR fetched IS NULL OR fetched>checked OR checked>(payload->>'checked_at')::timestamptz THEN RAISE EXCEPTION 'Invalid source check'; END IF;
  SELECT * INTO old FROM evidence_v2_snapshots WHERE source_id=src->>'source_id' AND content_sha256=sn->>'content_sha256';
  IF FOUND THEN
   sid:=old.snapshot_id;
   IF old.source_config-'enabled' IS DISTINCT FROM src-'enabled' OR old.ipv6_skipped<>(sn->>'ipv6_skipped')::bigint OR old.publisher_at IS DISTINCT FROM published OR old.ipv4_count<>jsonb_array_length(sn->'records') THEN RAISE EXCEPTION 'Conflicting content snapshot'; END IF;
   SELECT coalesce(jsonb_agg(jsonb_build_object('record_key',record_key,'network',network::text,'provider',provider,'basis',basis,'role',role,'hostname',hostname,'method',method,'service_category',service_category,'metadata',metadata) ORDER BY record_key),'[]'::jsonb) INTO existing_records FROM evidence_v2_indicators WHERE snapshot_id=sid;
   IF existing_records IS DISTINCT FROM (SELECT coalesce(jsonb_agg(r ORDER BY r->>'record_key'),'[]'::jsonb) FROM jsonb_array_elements(sn->'records') r) THEN RAISE EXCEPTION 'Conflicting records under content hash'; END IF;
   IF checked<old.checked_at THEN RAISE EXCEPTION 'Check time moved backwards'; END IF;
   UPDATE evidence_v2_snapshots SET checked_at=checked WHERE snapshot_id=sid;
  ELSE
   changed:=true; sid:=gen_random_uuid();
   INSERT INTO evidence_v2_snapshots VALUES(sid,src->>'source_id',sn->>'content_sha256',rh,src,fetched,checked,published,jsonb_array_length(sn->'records'),(sn->>'ipv6_skipped')::bigint,DEFAULT);
   FOR rec IN SELECT * FROM jsonb_array_elements(sn->'records') LOOP
    INSERT INTO evidence_v2_indicators VALUES(sid,rec->>'record_key',(rec->>'network')::cidr,rec->>'provider',rec->>'basis',rec->>'role',rec->>'hostname',rec->>'method',rec->>'service_category',rec->'metadata');
   END LOOP;
  END IF;
  IF previous_active->>(src->>'source_id') IS DISTINCT FROM sid::text THEN changed:=true; END IF;
  INSERT INTO evidence_v2_active(source_id,registry_sha256,snapshot_id) VALUES(src->>'source_id',rh,sid);
  seen:=seen+1;
 END LOOP;
 IF seen<>enabled_count THEN RAISE EXCEPTION 'Incomplete publication'; END IF;
 RETURN jsonb_build_object('status',CASE WHEN changed THEN 'loaded' ELSE 'unchanged' END,'registry_sha256',rh,'sources',evidence_v2_sources_public()->'sources');
END $$;

CREATE OR REPLACE FUNCTION evidence_v2_observe(payload jsonb) RETURNS jsonb LANGUAGE plpgsql VOLATILE AS $$
DECLARE m jsonb:=payload->'measurement'; r jsonb:=payload->'review'; ident uuid; old evidence_v2_observations;
 checked timestamptz; expiry timestamptz; did_change boolean:=false; old_review evidence_v2_reviews;
BEGIN
 IF jsonb_typeof(m) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Expected normalized measurement'; END IF;
 ident:=(m->>'observation_id')::uuid;
 checked:=evidence_v2_stamp(m->>'observed_at'); expiry:=(m->>'expires_at')::timestamptz;
 SELECT * INTO old FROM evidence_v2_observations WHERE observation_id=ident;
 IF FOUND THEN
  IF old.measurement IS DISTINCT FROM m THEN RAISE EXCEPTION 'Conflicting observation identity'; END IF;
 ELSE
  IF statement_timestamp()>=expiry THEN RAISE EXCEPTION 'Expired measurement'; END IF;
  INSERT INTO evidence_v2_observations VALUES(ident,m->>'observation_sha256',m->>'profile_sha256',(m->>'network')::cidr,checked,expiry,m);
  did_change:=true;
 END IF;
 IF r IS NOT NULL AND r<>'null'::jsonb THEN
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR r->>'observation_id' IS DISTINCT FROM ident::text OR r->>'observation_sha256' IS DISTINCT FROM m->>'observation_sha256' THEN RAISE EXCEPTION 'Review binding mismatch'; END IF;
  SELECT * INTO old_review FROM evidence_v2_reviews WHERE observation_id=ident;
  IF FOUND THEN
   IF old_review.observation_sha256 IS DISTINCT FROM r->>'observation_sha256' OR old_review.review_state IS DISTINCT FROM r->>'review_state' OR old_review.reviewed_at IS DISTINCT FROM evidence_v2_stamp(r->>'reviewed_at') OR old_review.reviewer_sha256 IS DISTINCT FROM r->>'reviewer_sha256' THEN RAISE EXCEPTION 'Conflicting immutable review'; END IF;
  ELSE
   INSERT INTO evidence_v2_reviews VALUES(ident,r->>'observation_sha256',r->>'review_state',evidence_v2_stamp(r->>'reviewed_at'),r->>'reviewer_sha256');
   did_change:=true;
  END IF;
 END IF;
 RETURN jsonb_build_object('status',CASE WHEN did_change THEN 'published' ELSE 'unchanged' END,'observation_id',ident,'expires_at',expiry);
END $$;

CREATE OR REPLACE FUNCTION evidence_v2_complete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME IN ('evidence_v2_head','evidence_v2_active') THEN
  IF EXISTS(SELECT FROM evidence_v2_head h JOIN evidence_v2_sources s USING(registry_sha256)
   WHERE s.enabled AND NOT EXISTS(SELECT FROM evidence_v2_active a WHERE a.registry_sha256=h.registry_sha256 AND a.source_id=s.source_id))
  THEN RAISE EXCEPTION 'Incomplete active registry'; END IF;
 ELSIF TG_TABLE_NAME='evidence_v2_snapshots' THEN
  IF EXISTS(SELECT FROM evidence_v2_snapshots s WHERE s.snapshot_id=NEW.snapshot_id AND
   (s.ipv4_count<>(SELECT count(*) FROM evidence_v2_indicators i WHERE i.snapshot_id=s.snapshot_id)
    OR (s.ipv4_count=0 AND s.source_config->>'adapter'<>'dns_a')))
  THEN RAISE EXCEPTION 'Snapshot record count mismatch'; END IF;
 END IF;
 RETURN NULL;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['evidence_v2_head','evidence_v2_active','evidence_v2_snapshots'] LOOP
  IF NOT EXISTS(SELECT FROM pg_trigger WHERE tgrelid=to_regclass(t) AND tgname='evidence_v2_complete_group') THEN
   EXECUTE format('CREATE CONSTRAINT TRIGGER evidence_v2_complete_group AFTER INSERT OR UPDATE OR DELETE ON %I DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION evidence_v2_complete()',t);
  END IF;
 END LOOP;
END $$;

-- Catalog fingerprint records exact columns, types, nullability, constraints, indexes,
-- triggers and contract function definitions, rather than trusting a version marker.
CREATE TABLE IF NOT EXISTS evidence_v2_manifest(singleton boolean PRIMARY KEY CHECK(singleton), definition jsonb NOT NULL);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['evidence_v2_registry','evidence_v2_sources','evidence_v2_snapshots','evidence_v2_indicators','evidence_v2_observations','evidence_v2_reviews','evidence_v2_manifest','evidence_v2_active'] LOOP
  IF NOT EXISTS(SELECT FROM pg_trigger WHERE tgrelid=to_regclass(t) AND tgname='evidence_v2_no_truncate') THEN
   EXECUTE format('CREATE TRIGGER evidence_v2_no_truncate BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION evidence_v2_immutable()',t);
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT FROM pg_trigger WHERE tgrelid='evidence_v2_manifest'::regclass AND tgname='evidence_v2_immutable_history') THEN
  CREATE TRIGGER evidence_v2_immutable_history BEFORE UPDATE OR DELETE ON evidence_v2_manifest FOR EACH ROW EXECUTE FUNCTION evidence_v2_immutable();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION evidence_v2_catalog() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'columns',(SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,coalesce(pg_get_expr(d.adbin,d.adrelid),'')) ORDER BY c.relname,a.attnum)
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname=current_schema() AND c.relkind='r' AND c.relname LIKE 'evidence_v2_%'),
 'constraints',(SELECT jsonb_agg(jsonb_build_array(c.relname,k.conname,pg_get_constraintdef(k.oid),k.convalidated) ORDER BY c.relname,k.conname) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname LIKE 'evidence_v2_%'),
 'indexes',(SELECT jsonb_agg(jsonb_build_array(c.relname,pg_get_indexdef(i.indexrelid),i.indisvalid) ORDER BY c.relname) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname LIKE 'evidence_v2_%'),
 'triggers',(SELECT jsonb_agg(jsonb_build_array(c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled) ORDER BY c.relname,t.tgname) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname LIKE 'evidence_v2_%' AND NOT t.tgisinternal),
 'functions',(SELECT jsonb_agg(pg_get_functiondef(p.oid) ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=current_schema() AND p.proname LIKE 'evidence_v2_%'))
$$;
CREATE OR REPLACE FUNCTION evidence_v2_validate(payload jsonb) RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('schema_version',1,'compatible',coalesce((SELECT definition=evidence_v2_catalog() FROM evidence_v2_manifest WHERE singleton),false))
$$;
INSERT INTO evidence_v2_manifest VALUES(true,evidence_v2_catalog()) ON CONFLICT DO NOTHING;
