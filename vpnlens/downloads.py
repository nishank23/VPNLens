"""Bounded downloads and dated CAIDA directory discovery."""

import os
import re
import tempfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROUTING_BASE = "https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/"
ORG_BASE = "https://publicdata.caida.org/datasets/as-organizations/"
ROUTING_NAME = re.compile(r"routeviews-rv2-(\d{8})-(\d{4})\.pfx2as\.gz")
ORG_NAME = re.compile(r"(\d{8})\.as-org2info\.txt\.gz")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def _request(url):
    if urlsplit(url).scheme != "https":
        raise ValueError("Downloads require HTTPS")
    return Request(url, headers={"User-Agent": "VPNLens-portfolio/1.0"})


def fetch_listing(url):
    with urlopen(_request(url), timeout=30) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("Directory listing exceeds 2 MB")
    parser = Links()
    parser.feed(payload.decode("utf-8"))
    return parser.links


def _valid_date(name, pattern):
    match = pattern.fullmatch(name)
    if not match:
        return False
    try:
        date = datetime.strptime(
            "".join(match.groups()),
            "%Y%m%d%H%M" if pattern is ROUTING_NAME else "%Y%m%d",
        )
    except ValueError:
        return False
    return date <= datetime.now(UTC).replace(tzinfo=None)


def discover_organization(listing=fetch_listing):
    files = [name for name in listing(ORG_BASE) if _valid_date(name, ORG_NAME)]
    if not files:
        raise ValueError("No dated organization snapshot found")
    return urljoin(ORG_BASE, max(files))


def discover_routing(listing=fetch_listing):
    year_now = datetime.now(UTC).year
    years = sorted(
        (
            name
            for name in listing(ROUTING_BASE)
            if re.fullmatch(r"\d{4}/", name) and 2000 <= int(name[:4]) <= year_now
        ),
        reverse=True,
    )
    for year in years:
        year_url = urljoin(ROUTING_BASE, year)
        months = sorted(
            (name for name in listing(year_url) if re.fullmatch(r"(0[1-9]|1[0-2])/", name)),
            reverse=True,
        )
        for month in months:
            month_url = urljoin(year_url, month)
            files = [name for name in listing(month_url) if _valid_date(name, ROUTING_NAME)]
            if files:
                return urljoin(month_url, max(files))
    raise ValueError("No dated IPv4 routing snapshot found")


def download_file(url, path, *, limit=512_000_000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with urlopen(_request(url), timeout=30) as response:
            if urlsplit(response.geturl()).scheme != "https":
                raise ValueError("HTTPS redirect required")
            expected = response.headers.get("Content-Length")
            expected = int(expected) if expected is not None else None
            if expected is not None and (expected <= 0 or expected > limit):
                raise ValueError("Invalid download length")
            size = 0
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".download-", delete=False
            ) as output:
                temporary = Path(output.name)
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise ValueError("Download exceeds size limit")
                    output.write(block)
            if not size or (expected is not None and size != expected):
                raise ValueError("Empty or incomplete download")
        os.replace(temporary, path)
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
