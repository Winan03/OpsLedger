from __future__ import annotations

import os


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no esta configurada en el entorno.")
    return database_url
