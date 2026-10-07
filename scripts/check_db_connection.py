from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import get_database_url

import psycopg


def load_database_url_from_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
            continue
        key, value = cleaned.split("=", 1)
        k = key.strip()
        if k not in os.environ:
            os.environ[k] = value.strip().strip('"').strip("'")


def get_psycopg_url() -> str:
    url = get_database_url()
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url


def main() -> None:
    load_database_url_from_dotenv()
    with psycopg.connect(get_psycopg_url(), connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            row = cursor.fetchone()
            print(row[0] if row else "Sin resultado")


if __name__ == "__main__":
    main()
