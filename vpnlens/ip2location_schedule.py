"""Official token downloads with monthly eligibility, independent of UI login."""

import os
from datetime import date
from hashlib import sha256
from urllib.parse import urlencode


def configured_download_url():
    explicit = os.getenv("IP2LOCATION_DOWNLOAD_URL", "").strip()
    if explicit:
        return explicit
    token = os.getenv("IP2LOCATION_DOWNLOAD_TOKEN", "").strip()
    if not token:
        return None
    return "https://www.ip2location.com/download?" + urlencode({"token": token, "file": "DB11LITE"})


def monthly_download_date(identity, year, month):
    # Spread installations across the first week without a new persisted setting.
    digest = sha256(f"ip2location:{identity}:{year:04d}-{month:02d}".encode()).hexdigest()
    return date(year, month, 1 + int(digest[:8], 16) % 7)


def download_eligibility(previous, when, identity, available):
    year, month = when.year, when.month
    following = monthly_download_date(
        identity, year + 1 if month == 12 else year, 1 if month == 12 else month + 1
    )
    if not available or not previous.get("download_month"):
        return True, following
    if previous["download_month"] == f"{year:04d}-{month:02d}":
        return False, following
    scheduled = monthly_download_date(identity, year, month)
    due = when.date() >= scheduled
    return due, following if due else scheduled
