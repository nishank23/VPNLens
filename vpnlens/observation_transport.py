"""Explicit, bounded, TLS-verified IPv4 echo transport with no proxy fallback."""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from vpnlens.evidence_contract import digest, stamp
from vpnlens.observation_contract import (
    ECHO,
    profile_contract,
    public_host,
    receipt_contract,
    strict_json,
)


def fetch_receipt(profile, *, baseline=False, client_factory=httpx.Client, clock=None):
    """Measure exactly the requested route; never expose transport exception secrets."""
    profile = profile_contract(profile)
    if profile["transport"] == "browser_import":
        raise ValueError("Browser observations require original exported receipts")
    clock = clock or (lambda: datetime.now(UTC))
    proxy = None
    if profile["transport"] == "explicit_http_proxy" and not baseline:
        proxy = os.environ.get(profile["proxy_env"])
        if not proxy:
            raise ValueError("Proxy environment reference is unset")
        try:
            parsed = urlsplit(proxy)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or "?" in proxy
                or "#" in proxy
                or "\\" in proxy
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in proxy)
            ):
                raise ValueError("Invalid proxy URL")
            parsed.port
        except ValueError:
            raise ValueError("Invalid proxy URL") from None
    started = stamp(clock())
    try:
        with client_factory(
            proxy=proxy, trust_env=False, follow_redirects=False, timeout=10, verify=True
        ) as client:
            with client.stream("GET", ECHO, headers={"Cache-Control": "no-cache"}) as response:
                if response.status_code != 200:
                    raise ValueError("Unexpected echo response status")
                payload = bytearray()
                for chunk in response.iter_bytes(chunk_size=4097):
                    if len(payload) + len(chunk) > 4096:
                        raise ValueError("Echo response exceeds byte limit")
                    payload.extend(chunk)
        observed = stamp(clock())
        body = payload.decode("utf-8", errors="strict")
        decoded = strict_json(body)
        if not isinstance(decoded, dict):
            raise ValueError("Expected echo JSON object")
        ip = public_host(decoded.get("ip"))
        receipt = {
            "receipt_id": str(uuid4()),
            "ip": ip,
            "endpoint": ECHO,
            "response_body": body,
            "response_sha256": digest(bytes(payload)),
            "started_at": started,
            "observed_at": observed,
        }
        receipt_contract(receipt, datetime.fromisoformat(observed))
        return receipt
    except Exception:
        # HTTPX may include credential-bearing proxy URLs in exception text.
        raise ValueError("Echo receipt capture failed") from None
