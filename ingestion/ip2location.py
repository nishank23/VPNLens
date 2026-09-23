import csv
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = os.getenv(
    "IP2LOCATION_CSV",
    "data/IP2LOCATION-LITE-DB11.CSV"
)
# CSV_FILE = os.getenv(
#     "test",
#     "data/test.CSV"
# )
DATABASE_URL = os.getenv("DATABASE_URL")


def ingest_ip2location():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            with open(CSV_FILE, "r", encoding="utf-8") as file:
                cur.execute("TRUNCATE TABLE raw_ip2location;")
                with cur.copy(
                    """
                    COPY raw_ip2location (
                        ip_from,
                        ip_to,
                        country_code,
                        country_name,
                        region_name,
                        city_name,
                        latitude,
                        longitude,
                        zip_code,
                        time_zone
                    )
                    FROM STDIN
                    WITH (FORMAT CSV, HEADER FALSE)
                    """
                ) as copy:
                    for row in file:
                        copy.write(row)
                cur.execute("SELECT COUNT(*) FROM raw_ip2location;")
                loaded_rows = cur.fetchone()[0]
                print(f"Inserted {loaded_rows} rows into raw_ip2location table.")
                if loaded_rows == 0:
                    raise ValueError("No data was inserted into the raw_ip2location table.")
        
        
        conn.commit()

    print("IP2Location data loaded successfully.")


if __name__ == "__main__":
    ingest_ip2location()
