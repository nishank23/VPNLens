"""DB-IP City Lite input and the committed geolocation release."""

import re
from datetime import UTC, datetime
from ipaddress import ip_address

from psycopg.rows import dict_row

IP2LOCATION = "ip2location"
DBIP_CITY_LITE = "dbip_city_lite"
DBIP_FILE = re.compile(r"dbip-city-lite-([0-9]{4})-([0-9]{2})[.]csv(?:[.]gz)?")


def dbip_download_url(when):
    return f"https://download.db-ip.com/free/dbip-city-lite-{when:%Y-%m}.csv.gz"


def dbip_release_date(name):
    match = DBIP_FILE.fullmatch(name)
    if match is None:
        raise ValueError("Expected dbip-city-lite-YYYY-MM.csv or .csv.gz")
    year, month = map(int, match.groups())
    return datetime(year, month, 1, tzinfo=UTC)


def dbip_ipv4_fields(fields):
    if len(fields) != 8:
        raise ValueError("DB-IP City Lite row must have 8 fields")
    start, end = ip_address(fields[0]), ip_address(fields[1])
    if start.version != end.version or start > end:
        raise ValueError("Invalid DB-IP address range")
    if start.version == 6:
        return None

    _, _, _, country, region, city, lat, lon = fields
    # Align with the legacy stage. The transformer maps "-" to SQL NULL.
    return (
        int(start),
        int(end),
        country or "-",
        "-",
        region or "-",
        city or "-",
        lat,
        lon,
        "-",
        "-",
    )


def dbip_snapshot(connection):
    with connection.cursor(row_factory=dict_row) as cursor:
        table = cursor.execute(
            "SELECT to_regclass('dbip_geolocation_release') AS release_table"
        ).fetchone()
        if table["release_table"] is None:
            return None
        return cursor.execute(
            """SELECT %s AS provider, source_file, snapshot_at FROM dbip_geolocation_release""",
            (DBIP_CITY_LITE,),
        ).fetchone()
