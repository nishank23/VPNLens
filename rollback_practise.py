import os ,psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def rollback_ip2location():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE test_clean(id INTEGER);")
            cur.execute("INSERT INTO test_clean(id) VALUES (1);")
            cur.execute("CREATE TEMP TABLE test_raw(id INTEGER);")
        conn.commit()
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("TRUNCATE TABLE test_clean;")
                    cur.execute("INSERT INTO test_clean(id) SELECT id FROM test_raw;")
                    cur.execute("""
                                SELECT
                                    (SELECT COUNT(*) FROM test_raw) as raw_rows,
                                    (SELECT COUNT(*) FROM test_clean) as clean_rows,
                                    (SELECT COUNT(*) FROM test_raw) = (SELECT COUNT(*) FROM test_clean) as row_counts_match
                                """)

                    raw_rows, clean_rows, row_counts_match = cur.fetchone()
                    if raw_rows == 0 or not row_counts_match:
                        raise ValueError(
                            f"Validation failed: raw={raw_rows}, clean={clean_rows}"
                        )
        except ValueError as e:
           print(f"Expected validation failure: {e}")

        with conn.cursor() as cur:
            cur.execute("SELECT id from test_clean ORDER BY id")
            data =cur.fetchall()
            print(f"Data in test_clean after rollback: {data}")



if __name__ == "__main__":
    rollback_ip2location()
