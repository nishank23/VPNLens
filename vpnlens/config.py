"""Explicit application configuration; never log database credentials."""

import os
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path

from dotenv import load_dotenv

from .geolocation import DBIP_CITY_LITE, IP2LOCATION

ROOT = Path(__file__).resolve().parents[1]


def evidence_enabled(value):
    """Parse only explicit supported flag values without echoing configuration."""
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in ("true", "1"):
            return True
        if normalized in ("false", "0"):
            return False
    raise ValueError("Invalid extended evidence flag")


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    connect_timeout: int = 5
    statement_timeout_ms: int = 5000
    cors_origins: tuple[str, ...] = ()
    extended_evidence: bool = False
    trusted_proxy_cidrs: tuple[str, ...] = ()
    api_requests_per_minute: int = 0
    api_total_requests_per_minute: int = 120
    geolocation_provider: str = IP2LOCATION

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            extended_evidence=evidence_enabled(os.getenv("VPNLENS_EXTENDED_EVIDENCE", "false")),
            connect_timeout=int(os.getenv("VPNLENS_CONNECT_TIMEOUT", "5")),
            statement_timeout_ms=int(os.getenv("VPNLENS_STATEMENT_TIMEOUT_MS", "5000")),
            cors_origins=tuple(
                x.strip() for x in os.getenv("VPNLENS_CORS_ORIGINS", "").split(",") if x.strip()
            ),
            geolocation_provider=os.getenv("VPNLENS_GEOLOCATION_PROVIDER", IP2LOCATION).strip(),
            api_requests_per_minute=int(os.getenv("VPNLENS_API_REQUESTS_PER_MINUTE", "0")),
            api_total_requests_per_minute=int(
                os.getenv("VPNLENS_API_TOTAL_REQUESTS_PER_MINUTE", "120")
            ),
            trusted_proxy_cidrs=tuple(
                x.strip()
                for x in os.getenv("VPNLENS_TRUSTED_PROXY_CIDRS", "").split(",")
                if x.strip()
            ),
        )

    def __post_init__(self):
        if self.geolocation_provider not in (IP2LOCATION, DBIP_CITY_LITE):
            raise ValueError("Unsupported geolocation provider")
        if not 1 <= self.connect_timeout <= 60 or not 1 <= self.statement_timeout_ms <= 120000:
            raise ValueError("Database timeouts are outside supported bounds")
        if "*" in self.cors_origins:
            raise ValueError("Configure explicit CORS origins rather than a wildcard")
        if not (
            1 <= self.api_total_requests_per_minute <= 10000
            and 0 <= self.api_requests_per_minute <= self.api_total_requests_per_minute
        ):
            raise ValueError("API rate limits are outside supported bounds")
        for value in self.trusted_proxy_cidrs:
            try:
                if not isinstance(value, str) or "/" not in value:
                    raise ValueError
                if ip_network(value, strict=True).prefixlen == 0:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    "Configure explicit trusted proxy CIDRs without wildcards"
                ) from None
