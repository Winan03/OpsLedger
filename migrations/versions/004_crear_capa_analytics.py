"""crear_capa_analytics

Revision ID: 004_capa_analytics
Revises: 003_tablas_operativas
Create Date: 2026-10-07 18:00:00.000000

"""
from __future__ import annotations

from alembic import op

revision = "004_capa_analytics"
down_revision = "003_tablas_operativas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. dim_fechas (generación de calendario)
    op.execute("""
        CREATE OR REPLACE VIEW analytics.dim_fechas AS
        SELECT 
            d::date AS fecha,
            EXTRACT(YEAR FROM d)::int AS anio,
            EXTRACT(MONTH FROM d)::int AS mes,
            EXTRACT(DAY FROM d)::int AS dia,
            EXTRACT(ISODOW FROM d)::int AS dia_semana,
            TO_CHAR(d, 'Day') AS nombre_dia,
            EXTRACT(WEEK FROM d)::int AS semana_iso,
            EXTRACT(QUARTER FROM d)::int AS trimestre,
            TO_CHAR(d, 'YYYY-MM') AS anio_mes
        FROM generate_series(
            '2016-01-01'::date,
            '2019-12-31'::date,
            '1 day'::interval
        ) d;
    """)

    # 2. dim_clientes
    op.execute("""
        CREATE OR REPLACE VIEW analytics.dim_clientes AS
        SELECT 
            cliente_id,
            cliente_unico_id,
            codigo_postal_prefijo,
            ciudad,
            estado_region AS cliente_estado
        FROM operativo.clientes;
    """)

    # 3. dim_vendedores
    op.execute("""
        CREATE OR REPLACE VIEW analytics.dim_vendedores AS
        SELECT 
            vendedor_id,
            codigo_postal_prefijo,
            ciudad,
            estado_region AS vendedor_estado
        FROM operativo.vendedores;
    """)

    # 4. dim_productos
    op.execute("""
        CREATE OR REPLACE VIEW analytics.dim_productos AS
        SELECT 
            p.producto_id,
            COALESCE(p.categoria_nombre, 'sin_categoria') AS categoria_nombre_portugues,
            COALESCE(c.categoria_nombre_ingles, 'sin_traduccion') AS categoria_nombre_ingles,
            p.longitud_nombre,
            p.longitud_descripcion,
            p.cantidad_fotos,
            p.peso_gramos,
            p.longitud_cm,
            p.altura_cm,
            p.ancho_cm
        FROM operativo.productos p
        LEFT JOIN operativo.categorias_producto c 
            ON p.categoria_nombre = c.categoria_nombre_portugues;
    """)

    # 5. fct_pedidos (centraliza exclusiones y métricas precalculadas)
    op.execute("""
        CREATE OR REPLACE VIEW analytics.fct_pedidos AS
        SELECT 
            p.pedido_id,
            p.cliente_id,
            p.estado_pedido,
            p.fecha_compra,
            p.fecha_aprobacion,
            p.fecha_entrega_transportista,
            p.fecha_entrega_cliente,
            p.fecha_estimada_entrega,
            p.banderas_calidad,
            -- Métricas precalculadas
            CASE 
                WHEN p.fecha_entrega_cliente IS NOT NULL AND p.fecha_compra IS NOT NULL 
                THEN EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_compra)) / 86400.0
                ELSE NULL 
            END AS tiempo_ciclo_dias,
            CASE 
                WHEN p.fecha_entrega_transportista IS NOT NULL AND p.fecha_aprobacion IS NOT NULL 
                THEN EXTRACT(EPOCH FROM (p.fecha_entrega_transportista - p.fecha_aprobacion)) / 86400.0
                ELSE NULL 
            END AS tiempo_despacho_dias,
            CASE 
                WHEN p.fecha_entrega_cliente IS NOT NULL AND p.fecha_estimada_entrega IS NOT NULL 
                THEN EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_estimada_entrega)) / 86400.0
                ELSE NULL 
            END AS desviacion_plazo_dias,
            (p.fecha_entrega_cliente <= p.fecha_estimada_entrega) AS es_a_tiempo,
            -- Banderas booleanas de validez analítica
            (
                p.estado_pedido = 'delivered' 
                AND p.fecha_entrega_cliente IS NOT NULL 
                AND NOT (p.banderas_calidad ? 'sin_fecha_entrega_cliente')
            ) AS es_valido_ciclo_otd,
            (
                p.fecha_entrega_transportista IS NOT NULL 
                AND p.fecha_aprobacion IS NOT NULL 
                AND NOT (p.banderas_calidad ? 'sin_fecha_aprobacion')
                AND NOT (p.banderas_calidad ? 'despacho_antes_de_aprobacion')
                AND NOT (p.banderas_calidad ? 'entrega_cliente_antes_de_transportista')
            ) AS es_valido_despacho,
            (p.estado_pedido NOT IN ('canceled', 'unavailable')) AS es_venta_bruta,
            (p.estado_pedido = 'delivered') AS es_ingreso_realizado
        FROM operativo.pedidos p;
    """)

    # 6. fct_items_pedido
    op.execute("""
        CREATE OR REPLACE VIEW analytics.fct_items_pedido AS
        SELECT 
            i.pedido_id,
            i.numero_item,
            i.producto_id,
            i.vendedor_id,
            i.fecha_limite_despacho,
            i.precio,
            i.valor_flete,
            (i.precio + i.valor_flete) AS total_item
        FROM operativo.items_pedido i;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.fct_items_pedido CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics.fct_pedidos CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics.dim_productos CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics.dim_vendedores CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics.dim_clientes CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics.dim_fechas CASCADE;")
