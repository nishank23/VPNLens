"""Bounded, consistent, read-only transactions for HTTP lookups."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import Settings


class SourcesUnavailable(Exception):
    pass


class SnapshotNotFound(Exception):
    pass


@contextmanager
def read_connection(settings: Settings):
    if not settings.database_url:
        raise SourcesUnavailable("Database is not configured")
    with psycopg.connect(
        settings.database_url,
        connect_timeout=settings.connect_timeout,
        row_factory=dict_row,
    ) as connection:
        connection.read_only = True
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        connection.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str(settings.statement_timeout_ms),),
        )
        yield connection
