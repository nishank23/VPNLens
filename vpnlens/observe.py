"""Produce immutable local exit measurement and review artifacts; publish only explicitly enabled approved measurements."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from vpnlens.config import ROOT, Settings
from vpnlens.evidence_contract import canonical, digest, instant, stamp, write_once
from vpnlens.evidence_store import observation_payload, publish_contract
from vpnlens.observation_contract import (
    baseline_contract,
    identifier,
    profile_contract,
    text,
    utc_now,
    validate_observation,
)
from vpnlens.observation_transport import fetch_receipt


def current_time():
    return datetime.now(UTC)


def read_json(path, limit=262144, archive_folder=None):
    """Read bounded bytes, archiving original bounded imports before JSON parsing."""
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON artifact exceeds byte limit")
    if archive_folder is not None:
        write_once(Path(archive_folder) / (digest(raw) + ".bin"), raw)
    from vpnlens.observation_contract import strict_json

    return strict_json(raw.decode("utf-8", errors="strict"))


def create_baseline(profile, probe):
    profile = profile_contract(profile)
    baseline = {
        "schema_version": 1,
        "kind": "baseline",
        "baseline_id": str(uuid4()),
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(canonical(profile)),
        "operator_attested_disconnected": True,
        "receipt": probe(profile, baseline=True),
    }
    baseline_contract(baseline, profile, current_time())
    return baseline


def create_observation(profile, baseline, probe, now):
    profile = profile_contract(profile)
    if profile["transport"] == "browser_import":
        raise ValueError("Browser receipts must be imported")
    before_probes = utc_now(now())
    before = baseline_contract(baseline, profile, before_probes)
    if before_probes - before > timedelta(minutes=15):
        raise ValueError("Baseline too old to capture")
    record = {
        "schema_version": 1,
        "kind": "exit_observation",
        "observation_id": str(uuid4()),
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(canonical(profile)),
        "method": profile["transport"],
        "review_state": "pending",
        "operator_attested_active": True,
        "baseline": baseline,
        "active_receipts": [probe(profile), probe(profile)],
    }
    validate_observation(record, profile, now())
    return record


def save_observation(folder, record):
    target = Path(folder) / "pending" / (identifier(record["observation_id"]) + ".json")
    write_once(target, canonical(record))
    return target


def approve_artifact(folder, record, profile, operator, now):
    """Record a separate approval without changing measurement time or expiry."""
    attributes = validate_observation(record, profile, now)
    operator = text(operator)
    observation_id = identifier(record["observation_id"])
    observation_sha256 = digest(canonical(record))
    target = Path(folder) / "reviews" / (observation_id + ".json")
    if target.exists():
        review = read_json(target)
        expected_keys = {
            "observation_id",
            "observation_sha256",
            "review_state",
            "operator",
            "reviewed_at",
        }
        if (
            not isinstance(review, dict)
            or set(review) != expected_keys
            or review["observation_id"] != observation_id
            or review["observation_sha256"] != observation_sha256
            or review["review_state"] != "approved"
        ):
            raise ValueError("Conflicting or invalid immutable review")
        text(review["operator"])
        reviewed_at = instant(review["reviewed_at"])
        if not instant(attributes["observed_at"]) <= reviewed_at <= utc_now(now):
            raise ValueError("Invalid review timing")
        return target
    review = {
        "observation_id": observation_id,
        "observation_sha256": observation_sha256,
        "review_state": "approved",
        "operator": operator,
        "reviewed_at": stamp(now),
    }
    write_once(target, canonical(review))
    return target


class RecorderParser(argparse.ArgumentParser):
    def error(self, message):
        # Argument errors can contain user-supplied credentials; expose only the class.
        raise ValueError("Invalid recorder arguments")


def main(argv=None):
    out = ROOT / "data" / "observations"
    try:
        parser = RecorderParser(description=__doc__)
        parser.add_argument("action", choices=("baseline", "capture", "import", "approve"))
        parser.add_argument("--profile", required=True)
        parser.add_argument("--profiles", type=Path, default=out / "profiles.json")
        parser.add_argument("--out", type=Path, default=out)
        parser.add_argument("--baseline", type=Path)
        parser.add_argument("--file", type=Path)
        parser.add_argument("--operator")
        parser.add_argument("--confirm-disconnected", action="store_true")
        parser.add_argument("--confirm-active", action="store_true")
        args = parser.parse_args(argv)
        out = args.out
        load_dotenv(ROOT / ".env")
        profiles = read_json(args.profiles)
        profile = profile_contract(profiles[args.profile])
        if args.profile != profile["profile_id"]:
            raise ValueError("Profile key must match profile ID")
        status = "local_artifact"
        if args.action == "baseline":
            if not args.confirm_disconnected:
                raise ValueError("Disconnected attestation required")
            record = create_baseline(profile, fetch_receipt)
            path = out / "baselines" / (record["baseline_id"] + ".json")
            write_once(path, canonical(record))
        elif args.action == "capture":
            if not args.confirm_active or args.baseline is None:
                raise ValueError("Active attestation and baseline required")
            record = create_observation(
                profile, read_json(args.baseline), fetch_receipt, current_time
            )
            path = save_observation(out, record)
        elif args.action == "import":
            if args.file is None or profile["transport"] != "browser_import":
                raise ValueError("Browser import profile and input file required")
            record = read_json(args.file, archive_folder=out / "imports")
            validate_observation(record, profile, current_time())
            path = save_observation(out, record)
        else:
            if args.file is None:
                raise ValueError("Approval input file required")
            text(args.operator)
            record = read_json(args.file)
            validate_observation(record, profile, current_time())
            save_observation(out, record)
            path = approve_artifact(out, record, profile, args.operator, current_time())
            settings = Settings.from_env()
            if settings.extended_evidence:
                # Re-read all immutable inputs after local review. Approval never probes.
                original = read_json(out / "pending" / (record["observation_id"] + ".json"))
                current_profiles = read_json(args.profiles)
                current_profile = profile_contract(current_profiles[args.profile])
                review = read_json(path)
                payload = observation_payload(original, current_profile, review, now=current_time())
                publish_contract(settings.database_url, "observe", payload)
                status = "published"
        print(json.dumps({"status": status, "path": str(path.resolve())}))
        return 0
    except Exception as error:
        error_type = type(error).__name__
        try:
            failure = {
                "kind": "recorder_failure",
                "at": stamp(current_time()),
                "error_type": error_type,
            }
            write_once(out / "failures" / (str(uuid4()) + ".json"), canonical(failure))
        except Exception as archive_error:
            print(f"failure_archive: {type(archive_error).__name__}", file=sys.stderr)
        print(error_type, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
