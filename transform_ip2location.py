import os ,csv, psycopg
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
sql_path = Path(__file__).resolve().parent / "sql" / "transformers.sql"

def transform_ip2location():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")
    with open(sql_path, "r", encoding="utf-8") as file:
        transformation_sql = file.read()
    with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(transformation_sql)
                cur.execute("""
                            SELECT
                                (SELECT COUNT(*) FROM raw_ip2location) AS raw_rows,
                                (SELECT COUNT(*) FROM ip2location) AS clean_rows,
                                (SELECT COUNT(*) FROM raw_ip2location)
                                = (SELECT COUNT(*) FROM ip2location) AS row_counts_match;
                            """)
                raw_rows, clean_rows, row_counts_match = cur.fetchone()
                if raw_rows == 0 or not row_counts_match:
                    raise ValueError(
                        f"Validation failed: raw={raw_rows}, clean={clean_rows}"
                    )
                
    print("Transformation committed successfully.")
                    

if __name__ == "__main__":
    transform_ip2location()                