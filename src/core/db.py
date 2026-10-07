from __future__ import annotations

from collections.abc import Iterator

import psycopg
from psycopg import Connection

from src.core.config import get_database_url


def open_connection() -> Iterator[Connection[tuple]]:
    with psycopg.connect(get_database_url(), connect_timeout=10) as connection:
        yield connection
