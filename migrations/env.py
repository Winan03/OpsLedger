from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#") and "=" in cleaned:
            key, val = cleaned.split("=", 1)
            k = key.strip()
            if k not in os.environ:
                os.environ[k] = val.strip().strip('"').strip("'")

from src.core.config import get_database_url

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Respect a URL already set programmatically (e.g. from tests).
# Only fall back to get_database_url() when the config still has the placeholder.
_PLACEHOLDER = "driver://user:pass@localhost/dbname"
_current_url = config.get_main_option("sqlalchemy.url")
if not _current_url or _current_url == _PLACEHOLDER:
    config.set_main_option("sqlalchemy.url", get_database_url())

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
