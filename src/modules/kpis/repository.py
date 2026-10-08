"""repository.py — Acceso a datos y consultas analíticas para KPIs.

Implementa las consultas parametrizadas sobre el esquema analytics / operativo.
Regla fundamental:
- Para filtros de categoría o vendedor en métricas a nivel de pedido/reseña (KPIs 1 a 4, 7 y 8),
  usa siempre EXISTS sobre items_pedido / productos para evitar multiplicar pedidos.
- Aplica la fecha y región de referencia correspondiente a cada KPI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from psycopg import Connection


@dataclass(frozen=True)
class FiltrosKPI:
    fecha_desde: date | datetime | None = None
    fecha_hasta: date | datetime | None = None
    estados_region: list[str] | None = None
    categoria_nombre: str | None = None  # en portugués, ej. 'beleza_saude' o 'sin_categoria'
    vendedor_id: str | None = None
    estado_pedido: str | None = None


# ---------------------------------------------------------------------------
# Helpers para construcción dinámica y segura de cláusulas WHERE
# ---------------------------------------------------------------------------

def _construir_filtro_exists(categoria: str | None, vendedor_id: str | None, alias_pedido: str = "p") -> tuple[str, list[Any]]:
    """Genera subquery EXISTS para filtrar pedidos sin duplicar filas."""
    if not categoria and not vendedor_id:
        return "", []

    clauses = [f"i.pedido_id = {alias_pedido}.pedido_id"]
    params: list[Any] = []

    if vendedor_id:
        clauses.append("i.vendedor_id = %s")
        params.append(vendedor_id)

    if categoria:
        if categoria == "sin_categoria":
            clauses.append("pr.categoria_nombre IS NULL")
        else:
            clauses.append("pr.categoria_nombre = %s")
            params.append(categoria)

    joins = "operativo.items_pedido i"
    if categoria:
        joins += " JOIN operativo.productos pr ON i.producto_id = pr.producto_id"

    where_sub = " AND ".join(clauses)
    return f" AND EXISTS (SELECT 1 FROM {joins} WHERE {where_sub})", params


# ---------------------------------------------------------------------------
# KPI 1: Tiempo de ciclo del pedido (Lead Time)
# Ref: fecha_entrega_cliente / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi1_tiempo_ciclo(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = [
        "p.es_valido_ciclo_otd = TRUE",
    ]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_entrega_cliente >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_entrega_cliente <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")
    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        SELECT 
            COUNT(*)::int AS total_pedidos,
            ROUND(AVG(p.tiempo_ciclo_dias)::numeric, 2) AS tiempo_ciclo_medio_dias,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.tiempo_ciclo_dias)::numeric, 2) AS tiempo_ciclo_mediana_dias,
            ROUND(MIN(p.tiempo_ciclo_dias)::numeric, 2) AS tiempo_ciclo_min_dias,
            ROUND(MAX(p.tiempo_ciclo_dias)::numeric, 2) AS tiempo_ciclo_max_dias
        FROM analytics.fct_pedidos p
        JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_pedidos": row[0] or 0,
        "tiempo_ciclo_medio_dias": float(row[1]) if row[1] is not None else 0.0,
        "tiempo_ciclo_mediana_dias": float(row[2]) if row[2] is not None else 0.0,
        "min_dias": float(row[3]) if row[3] is not None else 0.0,
        "max_dias": float(row[4]) if row[4] is not None else 0.0,
    }


# ---------------------------------------------------------------------------
# KPI 2: Cumplimiento de entrega (OTD)
# Ref: fecha_entrega_cliente / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi2_otd(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["p.es_valido_ciclo_otd = TRUE"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_entrega_cliente >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_entrega_cliente <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")
    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        SELECT 
            COUNT(*)::int AS total_pedidos_entregados,
            COUNT(*) FILTER (WHERE p.es_a_tiempo)::int AS entregados_a_tiempo,
            COUNT(*) FILTER (WHERE NOT p.es_a_tiempo)::int AS entregados_tarde,
            ROUND((COUNT(*) FILTER (WHERE p.es_a_tiempo)::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS otd_pct
        FROM analytics.fct_pedidos p
        JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    total = row[0] or 0
    a_tiempo = row[1] or 0
    tarde = row[2] or 0
    otd = float(row[3]) if row[3] is not None else 0.0
    return {
        "total_pedidos_entregados": total,
        "entregados_a_tiempo": a_tiempo,
        "entregados_tarde": tarde,
        "otd_pct": otd,
    }


# ---------------------------------------------------------------------------
# KPI 3: Desviación de plazo de entrega
# Ref: fecha_entrega_cliente / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi3_desviacion_plazo(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["p.es_valido_ciclo_otd = TRUE"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_entrega_cliente >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_entrega_cliente <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")
    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        SELECT 
            COUNT(*)::int AS total_pedidos,
            ROUND(AVG(p.desviacion_plazo_dias)::numeric, 2) AS desviacion_media_global_dias,
            ROUND(AVG(p.desviacion_plazo_dias) FILTER (WHERE NOT p.es_a_tiempo)::numeric, 2) AS retraso_medio_tardios_dias,
            ROUND(AVG(p.desviacion_plazo_dias) FILTER (WHERE p.es_a_tiempo)::numeric, 2) AS adelanto_medio_anticipados_dias,
            COUNT(*) FILTER (WHERE NOT p.es_a_tiempo)::int AS total_pedidos_tardios
        FROM analytics.fct_pedidos p
        JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_pedidos": row[0] or 0,
        "desviacion_media_global_dias": float(row[1]) if row[1] is not None else 0.0,
        "retraso_medio_tardios_dias": float(row[2]) if row[2] is not None else 0.0,
        "adelanto_medio_anticipados_dias": float(row[3]) if row[3] is not None else 0.0,
        "total_pedidos_tardios": row[4] or 0,
    }


# ---------------------------------------------------------------------------
# KPI 4: Tiempo de despacho del vendedor (Fulfillment)
# Ref: fecha_entrega_transportista / vendedor_estado
# ---------------------------------------------------------------------------

def consultar_kpi4_despacho_vendedor(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["p.es_valido_despacho = TRUE"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_entrega_transportista >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_entrega_transportista <= %s")
        params.append(filtros.fecha_hasta)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")

    # Si hay filtro de región, aplica sobre el vendedor del ítem
    if filtros.estados_region:
        where_parts.append("""
            EXISTS (
                SELECT 1 FROM operativo.items_pedido iv
                JOIN operativo.vendedores v ON iv.vendedor_id = v.vendedor_id
                WHERE iv.pedido_id = p.pedido_id AND v.estado_region = ANY(%s)
            )
        """)
        params.append(filtros.estados_region)

    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        SELECT 
            COUNT(*)::int AS total_pedidos_evaluados,
            ROUND(AVG(p.tiempo_despacho_dias)::numeric, 2) AS despacho_medio_dias,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.tiempo_despacho_dias)::numeric, 2) AS despacho_mediana_dias
        FROM analytics.fct_pedidos p
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_pedidos_evaluados": row[0] or 0,
        "despacho_medio_dias": float(row[1]) if row[1] is not None else 0.0,
        "despacho_mediana_dias": float(row[2]) if row[2] is not None else 0.0,
    }


# ---------------------------------------------------------------------------
# KPI 5: Costo logístico relativo
# Ref: fecha_compra / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi5_costo_logistico(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["p.es_venta_bruta = TRUE"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_compra >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_compra <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)
    if filtros.categoria_nombre:
        if filtros.categoria_nombre == "sin_categoria":
            where_parts.append("pr.categoria_nombre_portugues = 'sin_categoria'")
        else:
            where_parts.append("pr.categoria_nombre_portugues = %s")
            params.append(filtros.categoria_nombre)
    if filtros.vendedor_id:
        where_parts.append("i.vendedor_id = %s")
        params.append(filtros.vendedor_id)

    where_sql = " AND ".join(where_parts)

    query = f"""
        SELECT 
            ROUND(SUM(i.precio)::numeric, 2) AS valor_total_productos,
            ROUND(SUM(i.valor_flete)::numeric, 2) AS valor_total_flete,
            ROUND((SUM(i.valor_flete) / NULLIF(SUM(i.precio), 0) * 100)::numeric, 2) AS costo_logistico_relativo_pct,
            COUNT(DISTINCT p.pedido_id)::int AS total_pedidos
        FROM analytics.fct_items_pedido i
        JOIN analytics.fct_pedidos p ON i.pedido_id = p.pedido_id
        JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
        JOIN analytics.dim_productos pr ON i.producto_id = pr.producto_id
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    val_prod = float(row[0]) if row[0] is not None else 0.0
    val_flete = float(row[1]) if row[1] is not None else 0.0
    pct = float(row[2]) if row[2] is not None else 0.0
    return {
        "valor_total_productos": val_prod,
        "valor_total_flete": val_flete,
        "costo_logistico_relativo_pct": pct,
        "total_pedidos": row[3] or 0,
    }


# ---------------------------------------------------------------------------
# KPI 6: Ventas brutas, ingresos realizados y ticket promedio (AOV)
# Ref: fecha_compra / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi6_ingresos_y_ticket(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["p.es_venta_bruta = TRUE"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_compra >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_compra <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)
    if filtros.categoria_nombre:
        if filtros.categoria_nombre == "sin_categoria":
            where_parts.append("pr.categoria_nombre_portugues = 'sin_categoria'")
        else:
            where_parts.append("pr.categoria_nombre_portugues = %s")
            params.append(filtros.categoria_nombre)
    if filtros.vendedor_id:
        where_parts.append("i.vendedor_id = %s")
        params.append(filtros.vendedor_id)

    where_sql = " AND ".join(where_parts)

    query = f"""
        WITH items_filtrados AS (
            SELECT 
                p.pedido_id,
                p.es_ingreso_realizado,
                i.precio,
                i.valor_flete,
                i.total_item
            FROM analytics.fct_items_pedido i
            JOIN analytics.fct_pedidos p ON i.pedido_id = p.pedido_id
            JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
            JOIN analytics.dim_productos pr ON i.producto_id = pr.producto_id
            WHERE {where_sql}
        ),
        pedidos_agregados AS (
            SELECT 
                pedido_id,
                BOOL_OR(es_ingreso_realizado) AS es_ingreso_realizado,
                SUM(precio) AS total_prod_pedido,
                SUM(total_item) AS total_monto_pedido
            FROM items_filtrados
            GROUP BY pedido_id
        )
        SELECT 
            COUNT(*)::int AS total_pedidos_facturados,
            ROUND(SUM(total_monto_pedido)::numeric, 2) AS ventas_brutas_totales,
            ROUND(SUM(total_monto_pedido) FILTER (WHERE es_ingreso_realizado)::numeric, 2) AS ingresos_realizados_totales,
            ROUND(AVG(total_monto_pedido)::numeric, 2) AS ticket_promedio_total,
            ROUND(AVG(total_prod_pedido)::numeric, 2) AS ticket_promedio_productos
        FROM pedidos_agregados
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_pedidos_facturados": row[0] or 0,
        "ventas_brutas_totales": float(row[1]) if row[1] is not None else 0.0,
        "ingresos_realizados_totales": float(row[2]) if row[2] is not None else 0.0,
        "ticket_promedio_total": float(row[3]) if row[3] is not None else 0.0,
        "ticket_promedio_productos": float(row[4]) if row[4] is not None else 0.0,
    }


# ---------------------------------------------------------------------------
# KPI 7: Tasa de cancelación
# Ref: fecha_compra / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi7_tasa_cancelacion(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["1=1"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("p.fecha_compra >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("p.fecha_compra <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")
    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        SELECT 
            COUNT(*)::int AS total_pedidos,
            COUNT(*) FILTER (WHERE p.estado_pedido = 'canceled')::int AS pedidos_cancelados,
            COUNT(*) FILTER (WHERE p.estado_pedido = 'unavailable')::int AS pedidos_no_disponibles,
            ROUND((COUNT(*) FILTER (WHERE p.estado_pedido = 'canceled')::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS tasa_cancelacion_pct,
            ROUND((COUNT(*) FILTER (WHERE p.estado_pedido IN ('canceled', 'unavailable'))::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS tasa_falla_operativa_pct
        FROM analytics.fct_pedidos p
        JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
        WHERE {where_sql}
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_pedidos": row[0] or 0,
        "pedidos_cancelados": row[1] or 0,
        "pedidos_no_disponibles": row[2] or 0,
        "tasa_cancelacion_pct": float(row[3]) if row[3] is not None else 0.0,
        "tasa_falla_operativa_pct": float(row[4]) if row[4] is not None else 0.0,
    }


# ---------------------------------------------------------------------------
# KPI 8: Satisfacción del cliente (CSAT) vs. retraso
# Ref: fecha_creacion de la reseña / cliente_estado
# ---------------------------------------------------------------------------

def consultar_kpi8_satisfaccion_retraso(conn: Connection, filtros: FiltrosKPI | None = None) -> dict[str, Any]:
    filtros = filtros or FiltrosKPI()
    where_parts = ["1=1"]
    params: list[Any] = []

    if filtros.fecha_desde:
        where_parts.append("r.fecha_creacion >= %s")
        params.append(filtros.fecha_desde)
    if filtros.fecha_hasta:
        where_parts.append("r.fecha_creacion <= %s")
        params.append(filtros.fecha_hasta)
    if filtros.estados_region:
        where_parts.append("c.cliente_estado = ANY(%s)")
        params.append(filtros.estados_region)

    exists_clause, exists_params = _construir_filtro_exists(filtros.categoria_nombre, filtros.vendedor_id, "p")
    where_sql = " AND ".join(where_parts) + exists_clause
    params.extend(exists_params)

    query = f"""
        WITH resenas_segmentadas AS (
            SELECT 
                r.puntaje,
                CASE 
                    WHEN p.estado_pedido = 'canceled' THEN 'Cancelado'
                    WHEN p.fecha_entrega_cliente IS NULL THEN 'Sin entrega'
                    WHEN p.fecha_entrega_cliente <= p.fecha_estimada_entrega THEN 'A tiempo'
                    ELSE 'Con retraso'
                END AS segmento_entrega
            FROM operativo.resenas_pedido r
            JOIN analytics.fct_pedidos p ON r.pedido_id = p.pedido_id
            JOIN analytics.dim_clientes c ON p.cliente_id = c.cliente_id
            WHERE {where_sql}
        )
        SELECT 
            COUNT(*)::int AS total_resenas,
            ROUND(AVG(puntaje)::numeric, 2) AS csat_promedio_global,
            ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'A tiempo')::numeric, 2) AS csat_a_tiempo,
            ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'Con retraso')::numeric, 2) AS csat_con_retraso,
            ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'Cancelado')::numeric, 2) AS csat_cancelados,
            COUNT(*) FILTER (WHERE segmento_entrega = 'A tiempo')::int AS n_resenas_a_tiempo,
            COUNT(*) FILTER (WHERE segmento_entrega = 'Con retraso')::int AS n_resenas_con_retraso
        FROM resenas_segmentadas
    """
    row = conn.execute(query, params).fetchone()
    return {
        "total_resenas": row[0] or 0,
        "csat_promedio_global": float(row[1]) if row[1] is not None else 0.0,
        "csat_a_tiempo": float(row[2]) if row[2] is not None else 0.0,
        "csat_con_retraso": float(row[3]) if row[3] is not None else 0.0,
        "csat_cancelados": float(row[4]) if row[4] is not None else 0.0,
        "n_resenas_a_tiempo": row[5] or 0,
        "n_resenas_con_retraso": row[6] or 0,
    }


# ---------------------------------------------------------------------------
# Agregaciones de Series Temporales (Mensual o Semanal)
# ---------------------------------------------------------------------------

def consultar_tendencia_mensual_kpis(conn: Connection, anio: int | None = None) -> list[dict[str, Any]]:
    """Devuelve serie mensual con los KPIs principales usando dim_fechas."""
    where_sql = "WHERE f.fecha BETWEEN '2017-01-01' AND '2018-08-31'"
    params: list[Any] = []
    if anio:
        where_sql = "WHERE f.anio = %s"
        params.append(anio)

    query = f"""
        SELECT 
            TO_CHAR(p.fecha_compra, 'YYYY-MM') AS anio_mes,
            COUNT(DISTINCT p.pedido_id)::int AS pedidos_totales,
            ROUND((COUNT(*) FILTER (WHERE p.es_a_tiempo AND p.es_valido_ciclo_otd)::numeric / 
                   NULLIF(COUNT(*) FILTER (WHERE p.es_valido_ciclo_otd), 0) * 100), 2) AS otd_pct,
            ROUND(AVG(p.tiempo_ciclo_dias) FILTER (WHERE p.es_valido_ciclo_otd)::numeric, 2) AS lead_time_dias,
            ROUND((COUNT(*) FILTER (WHERE p.estado_pedido = 'canceled')::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS tasa_cancelacion_pct
        FROM analytics.fct_pedidos p
        JOIN analytics.dim_fechas f ON p.fecha_compra::date = f.fecha
        {where_sql}
        GROUP BY TO_CHAR(p.fecha_compra, 'YYYY-MM')
        ORDER BY anio_mes;
    """
    rows = conn.execute(query, params).fetchall()
    return [
        {
            "anio_mes": r[0],
            "pedidos_totales": r[1],
            "otd_pct": float(r[2]) if r[2] is not None else 0.0,
            "lead_time_dias": float(r[3]) if r[3] is not None else 0.0,
            "tasa_cancelacion_pct": float(r[4]) if r[4] is not None else 0.0,
        }
        for r in rows
    ]
