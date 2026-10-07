"""crear_tablas_operativas

Revision ID: 003_tablas_operativas
Revises: 002_tablas_staging
Create Date: 2026-10-07 16:20:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_tablas_operativas"
down_revision = "002_tablas_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. categorias_producto
    op.create_table(
        "categorias_producto",
        sa.Column("categoria_nombre_portugues", sa.String(length=100), nullable=False),
        sa.Column("categoria_nombre_ingles", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("categoria_nombre_portugues"),
        schema="operativo",
    )

    # 2. clientes
    op.create_table(
        "clientes",
        sa.Column("cliente_id", sa.String(length=50), nullable=False),
        sa.Column("cliente_unico_id", sa.String(length=50), nullable=False),
        sa.Column("codigo_postal_prefijo", sa.String(length=10), nullable=False),
        sa.Column("ciudad", sa.String(length=100), nullable=False),
        sa.Column("estado_region", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("cliente_id"),
        schema="operativo",
    )
    op.create_index(
        "idx_clientes_estado_ciudad",
        "clientes",
        ["estado_region", "ciudad"],
        schema="operativo",
    )
    op.create_index(
        "idx_clientes_unico_id",
        "clientes",
        ["cliente_unico_id"],
        schema="operativo",
    )

    # 3. vendedores
    op.create_table(
        "vendedores",
        sa.Column("vendedor_id", sa.String(length=50), nullable=False),
        sa.Column("codigo_postal_prefijo", sa.String(length=10), nullable=False),
        sa.Column("ciudad", sa.String(length=100), nullable=False),
        sa.Column("estado_region", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("vendedor_id"),
        schema="operativo",
    )
    op.create_index(
        "idx_vendedores_estado",
        "vendedores",
        ["estado_region"],
        schema="operativo",
    )

    # 4. productos
    op.create_table(
        "productos",
        sa.Column("producto_id", sa.String(length=50), nullable=False),
        sa.Column("categoria_nombre", sa.String(length=100), nullable=True),
        sa.Column("longitud_nombre", sa.Integer(), nullable=True),
        sa.Column("longitud_descripcion", sa.Integer(), nullable=True),
        sa.Column("cantidad_fotos", sa.Integer(), nullable=True),
        sa.Column("peso_gramos", sa.Integer(), nullable=True),
        sa.Column("longitud_cm", sa.Integer(), nullable=True),
        sa.Column("altura_cm", sa.Integer(), nullable=True),
        sa.Column("ancho_cm", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_nombre"],
            ["operativo.categorias_producto.categoria_nombre_portugues"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("producto_id"),
        schema="operativo",
    )
    op.create_index(
        "idx_productos_categoria",
        "productos",
        ["categoria_nombre"],
        schema="operativo",
    )

    # 5. pedidos
    op.create_table(
        "pedidos",
        sa.Column("pedido_id", sa.String(length=50), nullable=False),
        sa.Column("cliente_id", sa.String(length=50), nullable=False),
        sa.Column("estado_pedido", sa.String(length=30), nullable=False),
        sa.Column("fecha_compra", sa.DateTime(timezone=False), nullable=False),
        sa.Column("fecha_aprobacion", sa.DateTime(timezone=False), nullable=True),
        sa.Column("fecha_entrega_transportista", sa.DateTime(timezone=False), nullable=True),
        sa.Column("fecha_entrega_cliente", sa.DateTime(timezone=False), nullable=True),
        sa.Column("fecha_estimada_entrega", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "banderas_calidad",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado_pedido IN ('delivered', 'shipped', 'canceled', 'unavailable', 'invoiced', 'processing', 'created', 'approved')",
            name="chk_pedidos_estado",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["operativo.clientes.cliente_id"],
        ),
        sa.PrimaryKeyConstraint("pedido_id"),
        schema="operativo",
    )
    op.create_index(
        "idx_pedidos_fecha_compra",
        "pedidos",
        ["fecha_compra"],
        schema="operativo",
    )
    op.create_index(
        "idx_pedidos_estado_fecha",
        "pedidos",
        ["estado_pedido", "fecha_compra"],
        schema="operativo",
    )
    op.create_index(
        "idx_pedidos_cliente",
        "pedidos",
        ["cliente_id"],
        schema="operativo",
    )

    # 6. items_pedido
    op.create_table(
        "items_pedido",
        sa.Column("pedido_id", sa.String(length=50), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.String(length=50), nullable=False),
        sa.Column("vendedor_id", sa.String(length=50), nullable=False),
        sa.Column("fecha_limite_despacho", sa.DateTime(timezone=False), nullable=False),
        sa.Column("precio", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("valor_flete", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("precio >= 0", name="chk_items_precio_positivo"),
        sa.CheckConstraint("valor_flete >= 0", name="chk_items_flete_positivo"),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["operativo.pedidos.pedido_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["producto_id"],
            ["operativo.productos.producto_id"],
        ),
        sa.ForeignKeyConstraint(
            ["vendedor_id"],
            ["operativo.vendedores.vendedor_id"],
        ),
        sa.PrimaryKeyConstraint("pedido_id", "numero_item"),
        schema="operativo",
    )
    op.create_index(
        "idx_items_vendedor",
        "items_pedido",
        ["vendedor_id"],
        schema="operativo",
    )
    op.create_index(
        "idx_items_producto",
        "items_pedido",
        ["producto_id"],
        schema="operativo",
    )

    # 7. pagos_pedido
    op.create_table(
        "pagos_pedido",
        sa.Column("pedido_id", sa.String(length=50), nullable=False),
        sa.Column("secuencia_pago", sa.Integer(), nullable=False),
        sa.Column("tipo_pago", sa.String(length=30), nullable=False),
        sa.Column("cuotas_pago", sa.Integer(), server_default="1", nullable=False),
        sa.Column("monto_pago", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("monto_pago >= 0", name="chk_pagos_monto_positivo"),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["operativo.pedidos.pedido_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("pedido_id", "secuencia_pago"),
        schema="operativo",
    )

    # 8. resenas_pedido
    op.create_table(
        "resenas_pedido",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("resena_id", sa.String(length=50), nullable=False),
        sa.Column("pedido_id", sa.String(length=50), nullable=False),
        sa.Column("puntaje", sa.Integer(), nullable=False),
        sa.Column("titulo_comentario", sa.Text(), nullable=True),
        sa.Column("mensaje_comentario", sa.Text(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(timezone=False), nullable=False),
        sa.Column("fecha_respuesta", sa.DateTime(timezone=False), nullable=False),
        sa.CheckConstraint("puntaje BETWEEN 1 AND 5", name="chk_resenas_puntaje_rango"),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["operativo.pedidos.pedido_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resena_id", "pedido_id", name="uq_resenas_resena_pedido"),
        schema="operativo",
    )
    op.create_index(
        "idx_resenas_pedido",
        "resenas_pedido",
        ["pedido_id"],
        schema="operativo",
    )
    op.create_index(
        "idx_resenas_resena_id",
        "resenas_pedido",
        ["resena_id"],
        schema="operativo",
    )


def downgrade() -> None:
    op.drop_table("resenas_pedido", schema="operativo")
    op.drop_table("pagos_pedido", schema="operativo")
    op.drop_table("items_pedido", schema="operativo")
    op.drop_table("pedidos", schema="operativo")
    op.drop_table("productos", schema="operativo")
    op.drop_table("vendedores", schema="operativo")
    op.drop_table("clientes", schema="operativo")
    op.drop_table("categorias_producto", schema="operativo")
