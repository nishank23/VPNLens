import gzip,ipaddress,os,psycopg
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
file_path = Path("data/routeviews-rv2-20261001-1200.pfx2as.gz")
sourcefile = file_path.name
snapshot_at = datetime.strptime(sourcefile, "routeviews-rv2-%Y%m%d-%H%M.pfx2as.gz").replace(tzinfo=timezone.utc)
print(f"Snapshot at: {snapshot_at}")
print(f"Processing file: {sourcefile}")

def ingest_asn_prefixes():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            pass
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        for index, line in enumerate(f):
            if(index == 5):
                break
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
            print(f"Network: {network}")
       
