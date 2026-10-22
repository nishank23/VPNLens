import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def transform_asn_prefixes(source_file):
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")
    if not source_file:
        raise ValueError("source_file is required")

    sql_path = Path(__file__).resolve().parent / "sql" / "asn_transformers.sql"
    transformation_sql = sql_path.read_text(encoding="utf-8")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Count origin alternatives, not just source records.
            cur.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(cardinality(string_to_array(origin_as_raw, '_'))), 0)
                FROM raw_asn_prefixes
                WHERE source_file = %s
                """,
                (source_file,),
            )
            raw_rows, expected_rows = cur.fetchone()
            if raw_rows == 0 or expected_rows == 0:
                raise ValueError(f"No origin groups found for {source_file}")

            cur.execute(
                "DELETE FROM asn_prefix_origins WHERE source_file = %s",
                (source_file,),
            )
            cur.execute(transformation_sql, {"source_file": source_file})

            cur.execute(
                "SELECT COUNT(*) FROM asn_prefix_origins WHERE source_file = %s",
                (source_file,),
            )
            stored_rows = cur.fetchone()[0]
            if stored_rows != expected_rows:
                raise ValueError(
                    f"Row count mismatch: expected={expected_rows}, stored={stored_rows}"
                )

    print(
        f"Committed {stored_rows} origin groups from {raw_rows} raw rows "
        f"for {source_file}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transform one ASN snapshot.")
    parser.add_argument("source_file", help="Exact source_file value in raw_asn_prefixes")
    args = parser.parse_args()
    transform_asn_prefixes(args.source_file)
