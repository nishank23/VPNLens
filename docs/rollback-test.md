# Transformation rollback verification

This manual integration test exercises `transform_ip2location.py` against a separate database. It verifies recovery from an empty source, not every possible failure. The temporary-table exercise in `rollback_practise.py` demonstrates the transaction pattern separately and prints results for manual inspection.

## Prerequisites

Use the same Python environment as the working runner, with psycopg and python-dotenv installed. Run terminal commands from the project root. Keep the normal project database unchanged.

## Prepare the test database

Create `vpn_lens_test` once, outside an explicit transaction:

```sql
CREATE DATABASE vpn_lens_test;
```

Connect the SQL editor to that database and confirm:

```sql
SELECT current_database();
```

Proceed only if the result is `vpn_lens_test`. Run `sql/schema.sql` in that connection; it drops and recreates tables, so it must not be run against the project database for this test. Commit the schema setup if autocommit is disabled.

Leave `raw_ip2location` empty and create one committed clean row:

```sql
INSERT INTO ip2location (ip_from, ip_to, ip_range)
VALUES (100, 200, int8range(100, 200, '[]'));
COMMIT;
```

With autocommit enabled, the INSERT is already committed. For a repeat test, reset the test database tables using the same verified setup rather than inserting duplicate fixtures.

## Run the actual transformation

For the local passwordless PostgreSQL connection used during this exercise (replace the username if needed):

```bash
DATABASE_URL='postgresql://nishankbansal@localhost:5432/vpn_lens_test' python3 transform_ip2location.py
```

This command-scoped override leaves `.env` unchanged. The runner's default `load_dotenv()` behavior preserves the supplied environment value.

Expected: a nonzero process exit and:

```text
ValueError: Validation failed: raw=0, clean=0
```

The error is intentional. The empty INSERT is valid SQL, but Python rejects the empty result before the connection context commits.

## Verify rollback

In the test-database connection, query:

```sql
SELECT ip_from, ip_to, ip_range FROM ip2location;
SELECT COUNT(*) AS raw_rows FROM raw_ip2location;
```

Expected: exactly one clean row `(100, 200, [100,201))`, and zero raw rows. If the clean table is empty, the test failed even if an error was printed.

The user executed this test on 2026-09-26 and reported the expected validation error and preserved original clean row. This demonstrates that the actual runner rolled back the uncommitted clearing and replacement for empty input.
