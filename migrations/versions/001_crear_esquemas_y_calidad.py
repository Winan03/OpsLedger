"""crear_esquemas_y_calidad

Revision ID: 001_esquemas_calidad
Revises: 
Create Date: 2026-10-07 16:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_esquemas_calidad"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    op.execute("CREATE SCHEMA IF NOT EXISTS calidad;")
    op.execute("CREATE SCHEMA IF NOT EXISTS operativo;")
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics;")

    op.create_table(
        "cargas_archivos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("registros_totales", sa.Integer(), server_default="0", nullable=False),
        sa.Column("registros_procesados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("registros_rechazados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estado", sa.String(length=50), server_default="procesando", nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('procesando', 'completado', 'fallido')",
            name="chk_cargas_estado",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="calidad",
    )

    op.execute(
        "CREATE UNIQUE INDEX idx_cargas_hash_completado ON calidad.cargas_archivos (hash_sha256) WHERE estado = 'completado';"
    )

    op.create_table(
        "registros_rechazados",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("carga_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre_tabla_origen", sa.String(length=100), nullable=False),
        sa.Column("numero_fila", sa.BigInteger(), nullable=False),
        sa.Column("motivo_rechazo", sa.Text(), nullable=False),
        sa.Column("datos_crudos", postgresql.JSONB(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["carga_id"],
            ["calidad.cargas_archivos.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="calidad",
    )


def downgrade() -> None:
    op.drop_table("registros_rechazados", schema="calidad")
    op.execute("DROP INDEX IF EXISTS calidad.idx_cargas_hash_completado;")
    op.drop_table("cargas_archivos", schema="calidad")

    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS operativo CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS calidad CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE;")
