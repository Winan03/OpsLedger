from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from scripts.check_db_connection import load_database_url_from_dotenv
from src.core.config import get_test_database_url

import alembic.config
import alembic.command
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_test_psycopg_url() -> tuple[str, str]:
    load_database_url_from_dotenv()
    url = get_test_database_url()

    # Extract db name from URL
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")

    if not db_name.endswith("_test"):
        raise ValueError(
            f"TEST_DATABASE_URL apunta a '{db_name}'. "
            "Por seguridad, la base de datos de pruebas DEBE terminar en '_test' para evitar modificar la base de desarrollo."
        )

    if url.startswith("postgresql+psycopg://"):
        dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        dsn = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    else:
        dsn = url

    return url, dsn


def test_alembic_migrations_upgrade_and_downgrade_cleanly_on_test_db() -> None:
    raw_url, dsn = get_test_psycopg_url()

    # Configure Alembic to use TEST_DATABASE_URL
    alembic_cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", raw_url)

    # 1. Upgrade to head on opsledger_test
    alembic.command.upgrade(alembic_cfg, "head")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('staging', 'calidad', 'operativo');"
            )
            count_after_upgrade = cur.fetchone()[0]

    assert count_after_upgrade == 18

    # 2. Downgrade to base on opsledger_test
    alembic.command.downgrade(alembic_cfg, "base")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('staging', 'calidad', 'operativo');"
            )
            count_after_downgrade = cur.fetchone()[0]

    assert count_after_downgrade == 0

    # 3. Re-upgrade to head so test DB is ready
    alembic.command.upgrade(alembic_cfg, "head")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('staging', 'calidad', 'operativo');"
            )
            count_re_upgrade = cur.fetchone()[0]

    assert count_re_upgrade == 18
