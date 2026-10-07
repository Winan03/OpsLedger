"""crear_tablas_staging

Revision ID: 002_tablas_staging
Revises: 001_esquemas_calidad
Create Date: 2026-10-07 16:10:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_tablas_staging"
down_revision = "001_esquemas_calidad"
branch_labels = None
depends_on = None

STAGING_TABLES = {
    "stg_clientes": [
        "cliente_id",
        "cliente_unico_id",
        "codigo_postal_prefijo",
        "ciudad",
        "estado_region",
    ],
    "stg_vendedores": [
        "vendedor_id",
        "codigo_postal_prefijo",
        "ciudad",
        "estado_region",
    ],
    "stg_categorias_traduccion": [
        "categoria_nombre_portugues",
        "categoria_nombre_ingles",
    ],
    "stg_productos": [
        "producto_id",
        "categoria_nombre",
        "longitud_nombre",
        "longitud_descripcion",
        "cantidad_fotos",
        "peso_gramos",
        "longitud_cm",
        "altura_cm",
        "ancho_cm",
    ],
    "stg_pedidos": [
        "pedido_id",
        "cliente_id",
        "estado_pedido",
        "fecha_compra",
        "fecha_aprobacion",
        "fecha_entrega_transportista",
        "fecha_entrega_cliente",
        "fecha_estimada_entrega",
    ],
    "stg_items_pedido": [
        "pedido_id",
        "numero_item",
        "producto_id",
        "vendedor_id",
        "fecha_limite_despacho",
        "precio",
        "valor_flete",
    ],
    "stg_pagos_pedido": [
        "pedido_id",
        "secuencia_pago",
        "tipo_pago",
        "cuotas_pago",
        "monto_pago",
    ],
    "stg_resenas_pedido": [
        "resena_id",
        "pedido_id",
        "puntaje",
        "titulo_comentario",
        "mensaje_comentario",
        "fecha_creacion",
        "fecha_respuesta",
    ],
}


def upgrade() -> None:
    for table_name, columns in STAGING_TABLES.items():
        cols = [
            sa.Column(
                "id",
                sa.BigInteger(),
                sa.Identity(always=True),
                primary_key=True,
            ),
            sa.Column("carga_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("numero_fila", sa.BigInteger(), nullable=False),
        ]
        for col in columns:
            cols.append(sa.Column(col, sa.Text(), nullable=True))

        op.create_table(
            table_name,
            *cols,
            schema="staging",
        )


def downgrade() -> None:
    for table_name in reversed(list(STAGING_TABLES.keys())):
        op.drop_table(table_name, schema="staging")
