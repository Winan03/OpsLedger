from __future__ import annotations

import os


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no esta configurada en el entorno.")
    return database_url


def get_test_database_url() -> str:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        raise RuntimeError("TEST_DATABASE_URL no esta configurada en el entorno.")
    return test_database_url
