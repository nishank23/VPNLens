"""Documented output types for the future frontend."""

from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Literal

from pydantic import BaseModel


class Owner(BaseModel):
    asn: str
    org_name: str | None
    org_country_code: str | None
    org_snapshot_at: datetime | None
    org_source_file: str | None


class Security(BaseModel):
    vpn_status: Literal["listed", "unknown"]
    tor_status: Literal["listed", "unknown"]
    evidence: list[dict[str, Any]]
    active_source_count: int
    recently_checked_source_count: int
    stale_after_hours: int
    vpn_assessment: Literal["direct_association", "network_only", "unknown"] | None = None
    proxy_status: Literal["listed", "unknown"] | None = None
    residential_proxy_status: Literal["unknown"] | None = None
    residential_proxy_reason: str | None = None
    additional_evidence: list[dict[str, Any]] | None = None


class LookupRow(BaseModel):
    ip: IPv4Address
    country_code: str | None
    city_name: str | None
    prefix: IPv4Network | None
    origin_group: str | None
    snapshot_at: datetime | None
    asn_owners: list[Owner]
    security: Security


class Snapshot(BaseModel):
    source_file: str
    snapshot_at: datetime


class SelectedSources(BaseModel):
    routing: Snapshot
    organization: Snapshot


class LookupResponse(BaseModel):
    ip: IPv4Address
    selected_sources: SelectedSources
    results: list[LookupRow]
