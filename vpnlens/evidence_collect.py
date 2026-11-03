"""Prepare a public-evidence candidate without importing or changing active data."""

import argparse
import json
import sys
from pathlib import Path

from vpnlens.evidence_collectors import prepare_batch

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "config/evidence_sources.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data/evidence-v2")
    args = parser.parse_args(argv)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        candidate = prepare_batch(registry, args.out)
    except Exception as error:
        print(
            f"Collection failed ({type(error).__name__}); active data unchanged.", file=sys.stderr
        )
        return 1
    print(json.dumps({"status": "prepared", "candidate": str(candidate)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
