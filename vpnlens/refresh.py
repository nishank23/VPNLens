"""Refresh local datasets with independently atomic publication."""

import argparse
import csv
import gzip
import json
import logging
import math
import os
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from ipaddress import IPv4Network
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import psycopg

from ingestion.asn_organizations import ingest_asn_organizations
from ingestion.ip_evidence import refresh as refresh_evidence

from .config import ROOT, Settings
from .downloads import (
    ROUTING_NAME,
    discover_organization,
    discover_routing,
    download_file,
)
from .evidence_collectors import load_candidate, prepare_batch
from .evidence_store import publish_contract
from .ip2location_schedule import configured_download_url, download_eligibility

LOGGER = logging.getLogger("vpnlens.refresh")
DATASETS = ("routing", "organization", "geolocation", "evidence")
LOCKS = {"routing": 872410055, "organization": 872410056, "geolocation": 872410057}


def digest_file(path):
    digest = sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_key(connection):
    info = connection.info
    row = connection.execute("SELECT current_schema() AS schema").fetchone()
    schema = row["schema"] if isinstance(row, dict) else row[0]
    identity = [info.host, info.port, info.dbname, info.user, schema]
    return sha256(json.dumps(identity).encode()).hexdigest()[:24]


def state_path(connection, data_dir=None):
    return Path(data_dir or ROOT / "data") / "refresh" / (database_key(connection) + ".json")


def read_state(connection, data_dir=None):
    try:
        value = json.loads(state_path(connection, data_dir).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, prefix=".status-", delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(state, output, indent=2)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def publication(database_url, dataset):
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        if not connection.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", (LOCKS[dataset],)
        ).fetchone()[0]:
            raise RuntimeError("Dataset publication already running")
        yield connection


def load_routing(path, connection):
    path = Path(path)
    match = ROUTING_NAME.fullmatch(path.name)
    if not match:
        raise ValueError("Expected routeviews-rv2-YYYYMMDD-HHMM.pfx2as.gz")
    stamp = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M").replace(tzinfo=UTC)
    connection.execute("DELETE FROM raw_asn_prefixes WHERE source_file=%s", (path.name,))
    count = 0
    expected = 0
    with (
        gzip.open(path, "rt", encoding="utf-8") as source,
        connection.cursor() as cursor,
    ):
        with (
            cursor.copy("""COPY raw_asn_prefixes
            (prefix_address,prefix_length,origin_as_raw,source_file,snapshot_at) FROM STDIN""") as copy
        ):
            for number, line in enumerate(source, 1):
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) != 3:
                    raise ValueError(f"Invalid routing field count at line {number}")
                address, length, origins = fields
                network = IPv4Network(f"{address}/{length}", strict=True)
                alternatives = origins.split("_")
                if not all(
                    group
                    and all(
                        asn.isascii() and asn.isdigit() and 0 <= int(asn) <= 4294967295
                        for asn in group.split(",")
                    )
                    for group in alternatives
                ):
                    raise ValueError(f"Invalid ASN group at line {number}")
                copy.write_row(
                    (
                        str(network.network_address),
                        network.prefixlen,
                        origins,
                        path.name,
                        stamp,
                    )
                )
                count += 1
                expected += len(alternatives)
    if not count:
        raise ValueError("Routing snapshot is empty")
    connection.execute("DELETE FROM asn_prefix_origins WHERE source_file=%s", (path.name,))
    connection.execute((ROOT / "sql/asn_transformers.sql").read_text(), {"source_file": path.name})
    stored = connection.execute(
        "SELECT COUNT(*) FROM asn_prefix_origins WHERE source_file=%s", (path.name,)
    ).fetchone()[0]
    raw = connection.execute(
        "SELECT COUNT(*) FROM raw_asn_prefixes WHERE source_file=%s", (path.name,)
    ).fetchone()[0]
    if stored != expected or raw != count:
        raise ValueError("Routing row count mismatch")
    return {
        "source_file": path.name,
        "raw_rows": count,
        "rows": stored,
        "snapshot_at": stamp.isoformat(),
    }


@contextmanager
def geolocation_csv(path):
    path = Path(path)
    if path.suffix.lower() != ".zip":
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            yield source
        return
    with zipfile.ZipFile(path) as archive:
        candidates = []
        for member in archive.infolist():
            pure = PurePosixPath(member.filename)
            if pure.is_absolute() or ".." in pure.parts or "\\" in member.filename:
                raise ValueError("Unsafe ZIP member path")
            if member.flag_bits & 1 or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Encrypted or symlink ZIP member is not supported")
            if pure.suffix.lower() == ".csv" and not member.is_dir():
                candidates.append(member)
        if len(candidates) != 1 or not 0 < candidates[0].file_size <= 2_000_000_000:
            raise ValueError("ZIP must contain exactly one CSV within the 2 GB limit")
        import io

        with (
            archive.open(candidates[0]) as binary,
            io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as source,
        ):
            yield source


def load_geolocation(path, connection):
    count = 0
    previous = -1
    connection.execute("TRUNCATE raw_ip2location")
    with geolocation_csv(path) as source, connection.cursor() as cursor:
        with cursor.copy("""COPY raw_ip2location (ip_from,ip_to,country_code,country_name,
            region_name,city_name,latitude,longitude,zip_code,time_zone) FROM STDIN""") as copy:
            for fields in csv.reader(source):
                if len(fields) != 10:
                    raise ValueError("Geolocation row must have 10 fields")
                start, end = int(fields[0]), int(fields[1])
                lat, lon = float(fields[6]), float(fields[7])
                if not 0 <= start <= end <= 4294967295 or start <= previous:
                    raise ValueError("Unsorted, overlapping, or invalid geolocation range")
                if (
                    not math.isfinite(lat)
                    or not math.isfinite(lon)
                    or not -90 <= lat <= 90
                    or not -180 <= lon <= 180
                ):
                    raise ValueError("Invalid geolocation coordinates")
                copy.write_row((start, end, *fields[2:6], lat, lon, *fields[8:]))
                count += 1
                previous = end
                if count % 500000 == 0:
                    LOGGER.info("Validated geolocation rows=%s", count)
    if not count:
        raise ValueError("Geolocation dataset is empty")
    connection.execute((ROOT / "sql/transformers.sql").read_text())
    stored = connection.execute("SELECT COUNT(*) FROM ip2location").fetchone()[0]
    if count != stored:
        raise ValueError("Geolocation row count mismatch")
    return {"source_file": Path(path).name, "rows": stored, "snapshot_at": None}


def already_loaded(connection, dataset, source_file, expected_rows):
    if dataset == "routing":
        row = connection.execute(
            "SELECT COUNT(*) FROM asn_prefix_origins WHERE source_file=%s",
            (source_file,),
        ).fetchone()[0]
    elif dataset == "organization":
        row = connection.execute(
            "SELECT COUNT(*) FROM raw_asn_mappings WHERE source_file=%s", (source_file,)
        ).fetchone()[0]
    else:
        row = connection.execute("SELECT COUNT(*) FROM ip2location").fetchone()[0]
    if not row > 0 or row != expected_rows:
        return False
    if dataset == "routing":
        return connection.execute(
            "SELECT EXISTS(SELECT 1 FROM raw_asn_prefixes WHERE source_file=%s)",
            (source_file,),
        ).fetchone()[0]
    if dataset == "organization":
        return connection.execute(
            "SELECT EXISTS(SELECT 1 FROM raw_org_mappings WHERE source_file=%s)",
            (source_file,),
        ).fetchone()[0]
    return connection.execute("SELECT COUNT(*) FROM raw_ip2location").fetchone()[0] == row


def extended_registry():
    return json.loads((ROOT / "config/evidence_sources.json").read_text())


def refresh_datasets(
    database_url,
    *,
    datasets=DATASETS,
    routing_file=None,
    organization_file=None,
    geolocation_file=None,
    geolocation_url=None,
    data_dir=None,
    downloader=download_file,
    force_geolocation_download=False,
    extended_enabled=False,
    now=None,
):
    data_dir = Path(data_dir or ROOT / "data")
    if now is not None and now.tzinfo is None:
        raise ValueError("Refresh clock must include a timezone")

    def clock():
        return now.astimezone(UTC) if now is not None else datetime.now(UTC)

    if not datasets or any(item not in DATASETS for item in datasets):
        raise ValueError("Unsupported dataset selection")
    effective = []
    for item in datasets:
        effective.append(item)
        if item == "evidence" and extended_enabled:
            effective.append("evidence_extended")
    results = []
    # Session lock remains held across independent dataset transactions and state writes.
    with psycopg.connect(database_url, connect_timeout=5, autocommit=True) as lock:
        if not lock.execute("SELECT pg_try_advisory_lock(872410054)").fetchone()[0]:
            raise RuntimeError("Another refresh command is already running")
        state = read_state(lock, data_dir)
        identity = database_key(lock)
        status_path = state_path(lock, data_dir)
        for dataset in effective:
            LOGGER.info("Checking dataset=%s", dataset)
            checked = clock().isoformat()
            previous = state.get(dataset, {})
            try:
                if dataset == "evidence_extended":
                    registry = extended_registry()
                    folder = data_dir / "evidence-v2"
                    candidate = prepare_batch(registry, folder, clock=clock)
                    batch = load_candidate(candidate, folder, registry, now=clock())
                    record = publish_contract(database_url, "publish", batch)
                elif dataset == "evidence":
                    feeds = refresh_evidence(database_url, data_dir=data_dir / "evidence")
                    record = {
                        "status": "checked",
                        "sources": feeds,
                        "last_success_at": checked,
                    }
                else:
                    local = {
                        "routing": routing_file,
                        "organization": organization_file,
                        "geolocation": geolocation_file,
                    }[dataset]
                    remote_geo = (
                        dataset == "geolocation" and local is None and bool(geolocation_url)
                    )
                    manual = dataset == "geolocation" and not remote_geo
                    if remote_geo:
                        available = already_loaded(
                            lock, dataset, previous.get("source_file"), previous.get("rows")
                        )
                        due, next_date = download_eligibility(
                            previous, clock(), identity, available
                        )
                        if not due and not force_geolocation_download:
                            record = {
                                **previous,
                                "status": "not_due",
                                "last_checked_at": checked,
                                "manual_update_required": False,
                                "next_download_on": next_date.isoformat(),
                            }
                            state[dataset] = record
                            save_state(status_path, state)
                            results.append({"dataset": dataset, **record})
                            LOGGER.info(
                                "Geolocation monthly download not due; next scheduled date=%s",
                                next_date,
                            )
                            continue
                    if local is None:
                        if dataset == "geolocation" and not geolocation_url:
                            record = {
                                **previous,
                                "status": "manual_update_required",
                                "manual_update_required": True,
                                "last_checked_at": checked,
                            }
                            state[dataset] = record
                            save_state(status_path, state)
                            results.append({"dataset": dataset, **record})
                            LOGGER.info(
                                "Geolocation requires a local file or authorized download URL"
                            )
                            continue
                        url = (
                            geolocation_url
                            if dataset == "geolocation"
                            else (
                                discover_routing()
                                if dataset == "routing"
                                else discover_organization()
                            )
                        )
                        name = Path(urlsplit(url).path).name
                        if dataset == "geolocation":
                            # Do not persist credentialed URL paths or query strings.
                            name = "ip2location.zip"
                        local = downloader(url, data_dir / "downloads" / dataset / name)
                    path = Path(local).expanduser().resolve()
                    content_hash = digest_file(path)
                    if (
                        previous.get("sha256") == content_hash
                        and previous.get("source_file") == path.name
                        and already_loaded(lock, dataset, path.name, previous.get("rows"))
                    ):
                        record = {
                            **previous,
                            "status": "unchanged",
                            "manual_update_required": manual,
                            "last_success_at": checked,
                        }
                    else:
                        with publication(database_url, dataset) as connection:
                            if dataset == "routing":
                                loaded = load_routing(path, connection)
                            elif dataset == "organization":
                                loaded = ingest_asn_organizations(path, connection=connection)
                                loaded["rows"] = loaded["asn_rows"]
                            else:
                                loaded = load_geolocation(path, connection)
                            if digest_file(path) != content_hash:
                                raise ValueError("Source file changed during ingestion")
                        record = {
                            **loaded,
                            "sha256": content_hash,
                            "status": "loaded",
                            "manual_update_required": manual,
                            "last_success_at": checked,
                        }
                if dataset == "geolocation":
                    if remote_geo:
                        record["download_month"] = clock().strftime("%Y-%m")
                        record["downloaded_at"] = clock().isoformat()
                        record["next_download_on"] = next_date.isoformat()
                    else:
                        for key in ("download_month", "downloaded_at", "next_download_on"):
                            record.pop(key, None)
                record["last_checked_at"] = clock().isoformat()
                record["last_success_at"] = record["last_checked_at"]
                record.pop("last_error_type", None)
                state[dataset] = record
                save_state(status_path, state)
                results.append({"dataset": dataset, **record})
                LOGGER.info("Dataset=%s status=%s", dataset, record["status"])
            except Exception as error:
                state[dataset] = {
                    **previous,
                    "status": "failed",
                    "last_checked_at": checked,
                    "last_error_type": type(error).__name__,
                }
                save_state(status_path, state)
                LOGGER.error(
                    "Dataset=%s refresh failed type=%s; previous committed data retained",
                    dataset,
                    type(error).__name__,
                )
                raise
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("all", *DATASETS), default="all")
    parser.add_argument("--routing-file")
    parser.add_argument("--organization-file")
    parser.add_argument(
        "--geolocation-file", help="Authorized local IP2Location DB11 IPv4 CSV or ZIP"
    )
    parser.add_argument(
        "--force-geolocation-download",
        action="store_true",
        help="Recovery only: bypass the monthly limit for a configured download URL/token",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    settings = Settings.from_env()
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    geo = args.geolocation_file or os.getenv("IP2LOCATION_CSV")
    if geo and not Path(geo).is_absolute():
        geo = str(ROOT / geo)
    # A configured download URL takes priority over the fallback local file.
    url = configured_download_url()
    if args.force_geolocation_download and not url:
        parser.error("Configure IP2LOCATION_DOWNLOAD_TOKEN or IP2LOCATION_DOWNLOAD_URL first")
    if url and not args.geolocation_file:
        geo = None
    try:
        result = refresh_datasets(
            settings.database_url,
            datasets=DATASETS if args.dataset == "all" else (args.dataset,),
            routing_file=args.routing_file,
            organization_file=args.organization_file,
            geolocation_file=geo,
            geolocation_url=url,
            force_geolocation_download=args.force_geolocation_download,
            extended_enabled=settings.extended_evidence,
        )
        print(json.dumps(result, indent=2))
    except Exception as error:
        parser.exit(
            1,
            f"Refresh failed ({type(error).__name__}); see the dataset status and configuration.\n",
        )


if __name__ == "__main__":
    main()
