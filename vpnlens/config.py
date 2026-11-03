"""Explicit application configuration; never log database credentials."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

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
        )

    def __post_init__(self):
        if not 1 <= self.connect_timeout <= 60 or not 1 <= self.statement_timeout_ms <= 120000:
            raise ValueError("Database timeouts are outside supported bounds")
        if "*" in self.cors_origins:
            raise ValueError("Configure explicit CORS origins rather than a wildcard")
