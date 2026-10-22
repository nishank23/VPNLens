import gzip,ipaddress,os,psycopg
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
file_path = Path("data/routeviews-rv2-20261001-1200.pfx2as.gz")
source_file = file_path.name
snapshot_at = datetime.strptime(source_file, "routeviews-rv2-%Y%m%d-%H%M.pfx2as.gz").replace(tzinfo=timezone.utc)
print(f"Snapshot at: {snapshot_at}")
print(f"Processing file: {source_file}")

def ingest_asn_prefixes():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as curr:

            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                curr.execute("DELETE FROM raw_asn_prefixes WHERE source_file = %s",
                                (source_file,),
                            )
                loaded_rows = 0
                with curr.copy("""
                               COPY raw_asn_prefixes (
                                            prefix_address,
                                            prefix_length,
                                            origin_as_raw,
                                            source_file,
                                            snapshot_at
                                        )
                                        FROM STDIN
                                    """) as copy:


                    for index, line in enumerate(f):
                        fields = line.rstrip("\r\n").split("\t")

                        # Process the prefix and ASN as needed
                        if (len(fields) != 3):
                            raise ValueError(f"Unexpected number of fields in line {index + 1}: {line.strip()}")

                        prefix_address, prefix_length, origin_as_raw = fields
                        # Convert prefix length to integer

                        prefix_length = int(prefix_length)
                        if(prefix_length < 0 or prefix_length > 32):
                            raise ValueError(f"Invalid prefix length in line {index + 1}: {prefix_length}")

                        network = ipaddress.IPv4Network(f"{prefix_address}/{prefix_length}", strict=True)

                        copy.write_row([
                            prefix_address,
                            prefix_length,
                            origin_as_raw,
                            source_file,
                            snapshot_at
                        ])
                        loaded_rows += 1
            if loaded_rows ==0:
                raise ValueError("No rows were loaded into the raw_asn_prefixes table. Please check the input file.")

            curr.execute(
            "SELECT COUNT(*) FROM raw_asn_prefixes WHERE source_file = %s",
            (source_file,),)

            stored_rows = curr.fetchone()[0]
            if loaded_rows != stored_rows:
                raise ValueError(
                    f"Row count mismatch: loaded {loaded_rows}, stored {stored_rows}"
                )
            print(f"Loaded {loaded_rows} rows into raw_asn_prefixes table.")
            curr.execute(
                        "SELECT source_file, COUNT(*) as snapshot_rows FROM raw_asn_prefixes GROUP BY source_file",
                        )
            snapshot_counts = curr.fetchall()
            for filename, row_count in snapshot_counts:
                print(f"{filename}: {row_count} rows")
if __name__ == "__main__":
    ingest_asn_prefixes()
