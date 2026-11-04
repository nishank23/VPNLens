export interface Owner {
  asn: string;
  org_name: string | null;
  org_country_code: string | null;
  org_snapshot_at: string | null;
  org_source_file: string | null;
}
export type ConnectionTypeClaim = 'residential' | 'mobile' | 'datacenter' | 'unknown';
export type EvidenceRole = 'server' | 'exit' | 'unknown';
export type EvidenceBasis =
  'provider_list' | 'provider_dns' | 'network_inference' | 'exit_observation';
export interface AdditionalEvidence {
  source_id: string;
  family: string;
  record_key: string;
  network: string;
  provider: string | null;
  basis: EvidenceBasis;
  role: EvidenceRole;
  method: string;
  service_category: 'vpn' | 'proxy';
  source_url: string;
  checked_at: string;
  fetched_at: string;
  observed_at: string | null;
  expires_at: string | null;
  review_state: 'approved' | null;
  hostname: string | null;
  connection_type_claim?: ConnectionTypeClaim | null;
  operator_attested?: boolean;
  stale: boolean;
}
export interface Evidence {
  source_id: string;
  indicator_type: 'vpn_server' | 'tor_exit';
  provider: string | null;
  source_url: string;
  checked_at: string;
  fetched_at: string;
  stale: boolean;
  content_sha256?: string;
  record_key?: string;
  method?: string;
  role?: EvidenceRole;
  observed_at?: string | null;
  expires_at?: string | null;
  connection_type_claim?: ConnectionTypeClaim | null;
  operator_attested?: boolean;
}
export interface Security {
  vpn_assessment?: 'direct_association' | 'network_only' | 'unknown';
  proxy_status?: 'listed' | 'unknown';
  residential_proxy_status?: 'unknown';
  residential_proxy_reason?: string;
  additional_evidence?: AdditionalEvidence[];
  vpn_status: 'listed' | 'unknown';
  tor_status: 'listed' | 'unknown';
  evidence: Evidence[];
  active_source_count: number;
  recently_checked_source_count: number;
  stale_after_hours: number;
}
export interface LookupRow {
  ip: string;
  country_code: string | null;
  city_name: string | null;
  prefix: string | null;
  origin_group: string | null;
  snapshot_at: string | null;
  asn_owners: Owner[];
  security: Security;
}
export interface Snapshot {
  source_file: string;
  snapshot_at: string;
}
export interface GeolocationSnapshot extends Snapshot {
  provider: 'dbip_city_lite';
}
export interface LookupResponse {
  ip: string;
  selected_sources: {
    routing: Snapshot;
    organization: Snapshot;
    geolocation?: GeolocationSnapshot;
  };
  results: LookupRow[];
}
export type DecisionReason =
  | 'recent_vpn_evidence'
  | 'recent_tor_evidence'
  | 'recent_proxy_evidence'
  | 'no_recent_blocking_evidence'
  | 'insufficient_recent_evidence';
export interface AccessDecision {
  policy_id: 'streaming-access-v1';
  action: 'allow' | 'block';
  reason_codes: DecisionReason[];
  scheduled_source_health: 'ready' | 'degraded';
  evaluated_at: string;
}
export interface DecisionResponse {
  lookup: LookupResponse;
  decision: AccessDecision;
}
export interface FeedStatus {
  source_id: string;
  indicator_type: 'vpn_server' | 'tor_exit' | 'network_inference';
  basis?: EvidenceBasis;
  record_kind?: 'network' | 'host';
  provider: string | null;
  source_url: string;
  checked_at: string;
  fetched_at: string;
  ipv4_count: number;
  ipv6_skipped: number;
  stale: boolean;
}
export interface RefreshRecord {
  status: string;
  last_success_at?: string;
  last_checked_at?: string;
  next_download_on?: string;
  download_month?: string;
  manual_update_required?: boolean;
  rows?: number;
  source_file?: string;
}
export interface SourceResponse {
  security_expected_source_ids?: string[];
  geolocation: {
    available: boolean;
    snapshot_at: string | null;
    provider?: GeolocationSnapshot['provider'];
    source_file?: string;
  };
  routing: Snapshot[];
  organization: Snapshot[];
  security: FeedStatus[];
  security_stale_after_hours: number;
  refresh: Record<string, RefreshRecord>;
}
export interface Health {
  status: 'ready' | 'degraded' | 'not_ready';
  recently_checked_security_sources?: number;
  expected_security_sources?: number;
}
