"""repository.py — Acceso a datos para la ingesta ETL.

Toda sentencia SQL vive aquí.  El service orquesta; este módulo ejecuta.

Esquema real de calidad.cargas_archivos (migración 001):
  PK: id UUID (gen_random_uuid)
  nombre_archivo, hash_sha256, registros_totales, registros_procesados,
  registros_rechazados, estado, creado_en

Esquema real de calidad.registros_rechazados (migración 001):
  PK: id BIGINT IDENTITY
  carga_id UUID FK→cargas_archivos.id (RESTRICT)
  nombre_tabla_origen, numero_fila, motivo_rechazo, datos_crudos, creado_en
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import Connection


# ---------------------------------------------------------------------------
# Cargas de archivos
# ---------------------------------------------------------------------------

def registrar_carga(
    conn: Connection,
    nombre_archivo: str,
    hash_sha256: str,
    total_filas: int,
) -> uuid.UUID:
    """Inserta una carga en estado 'procesando' y devuelve su id (UUID)."""
    row = conn.execute(
        """
        INSERT INTO calidad.cargas_archivos
            (nombre_archivo, hash_sha256, registros_totales, estado)
        VALUES (%s, %s, %s, 'procesando')
        RETURNING id
        """,
        (nombre_archivo, hash_sha256, total_filas),
    ).fetchone()
    return row[0]


def existe_carga_completada(conn: Connection, hash_sha256: str) -> bool:
    """True si ya existe una carga completada con ese hash."""
    row = conn.execute(
        "SELECT 1 FROM calidad.cargas_archivos WHERE hash_sha256 = %s AND estado = 'completado'",
        (hash_sha256,),
    ).fetchone()
    return row is not None


def marcar_completado(
    conn: Connection,
    carga_id: uuid.UUID,
    procesados: int,
    rechazados: int,
) -> None:
    conn.execute(
        """
        UPDATE calidad.cargas_archivos
        SET estado = 'completado',
            registros_procesados = %s,
            registros_rechazados = %s
        WHERE id = %s
        """,
        (procesados, rechazados, carga_id),
    )


def marcar_fallido(conn: Connection, carga_id: uuid.UUID, motivo: str) -> None:
    conn.execute(
        "UPDATE calidad.cargas_archivos SET estado = 'fallido' WHERE id = %s",
        (carga_id,),
    )


def limpiar_cargas_procesando(conn: Connection) -> int:
    """Al iniciar, marca 'fallido' las cargas que sigan 'procesando'
    y elimina sus filas de staging.  Devuelve cuántas cargas afectó."""
    rows = conn.execute(
        "SELECT id FROM calidad.cargas_archivos WHERE estado = 'procesando'",
    ).fetchall()
    if not rows:
        return 0
    ids = [r[0] for r in rows]
    staging_tables = [
        "staging.stg_clientes",
        "staging.stg_vendedores",
        "staging.stg_categorias_traduccion",
        "staging.stg_productos",
        "staging.stg_pedidos",
        "staging.stg_items_pedido",
        "staging.stg_pagos_pedido",
        "staging.stg_resenas_pedido",
    ]
    for tabla in staging_tables:
        conn.execute(
            f"DELETE FROM {tabla} WHERE carga_id = ANY(%s)",  # noqa: S608
            (ids,),
        )
    conn.execute(
        "UPDATE calidad.cargas_archivos SET estado = 'fallido' WHERE id = ANY(%s)",
        (ids,),
    )
    return len(ids)


# ---------------------------------------------------------------------------
# Staging — insert fila a fila con pipeline
# ---------------------------------------------------------------------------

def copy_to_staging(
    conn: Connection,
    tabla: str,
    columnas: list[str],
    filas: list[dict[str, Any]],
    carga_id: uuid.UUID,
) -> None:
    """Inserta filas al staging usando psycopg pipeline.

    Args:
        tabla: nombre sin esquema, ej. "stg_clientes".
        columnas: columnas de datos (sin carga_id/numero_fila).
        filas: lista de dicts con clave = nombre de columna.
    """
    full_table = f"staging.{tabla}"
    all_cols = ["carga_id", "numero_fila"] + columnas
    col_str = ", ".join(all_cols)
    placeholders = ", ".join(["%s"] * len(all_cols))

    with conn.pipeline():
        for i, fila in enumerate(filas, start=1):
            valores = [carga_id, i] + [fila.get(c) for c in columnas]
            conn.execute(
                f"INSERT INTO {full_table} ({col_str}) VALUES ({placeholders})",  # noqa: S608
                valores,
            )


def limpiar_staging(conn: Connection, tabla: str, carga_id: uuid.UUID) -> None:
    conn.execute(
        f"DELETE FROM staging.{tabla} WHERE carga_id = %s",  # noqa: S608
        (carga_id,),
    )


# ---------------------------------------------------------------------------
# Registros rechazados
# ---------------------------------------------------------------------------

def insertar_rechazo(
    conn: Connection,
    carga_id: uuid.UUID,
    numero_fila: int,
    tabla_destino: str,
    motivo: str,
    datos_crudos: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO calidad.registros_rechazados
            (carga_id, nombre_tabla_origen, numero_fila, motivo_rechazo, datos_crudos)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        """,
        (carga_id, tabla_destino, numero_fila, motivo, json.dumps(datos_crudos, default=str)),
    )


# ---------------------------------------------------------------------------
# INSERT operativo — una función por tabla (cursor.executemany + pipeline)
# ---------------------------------------------------------------------------

def upsert_categorias(conn: Connection, filas: list[dict[str, Any]]) -> int:
    """INSERT ... ON CONFLICT DO NOTHING usando cursor.executemany en pipeline."""
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.categorias_producto
                    (categoria_nombre_portugues, categoria_nombre_ingles)
                VALUES (%s, %s)
                ON CONFLICT (categoria_nombre_portugues) DO NOTHING
                """,
                [(f["categoria_nombre_portugues"], f.get("categoria_nombre_ingles")) for f in filas],
            )
    return len(filas)


def upsert_clientes(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.clientes
                    (cliente_id, cliente_unico_id, codigo_postal_prefijo, ciudad, estado_region)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cliente_id) DO NOTHING
                """,
                [
                    (f["cliente_id"], f["cliente_unico_id"], f["codigo_postal_prefijo"],
                     f["ciudad"], f["estado_region"])
                    for f in filas
                ],
            )
    return len(filas)


def upsert_vendedores(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.vendedores
                    (vendedor_id, codigo_postal_prefijo, ciudad, estado_region)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (vendedor_id) DO NOTHING
                """,
                [(f["vendedor_id"], f["codigo_postal_prefijo"], f["ciudad"], f["estado_region"])
                 for f in filas],
            )
    return len(filas)


def upsert_productos(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.productos
                    (producto_id, categoria_nombre, longitud_nombre, longitud_descripcion,
                     cantidad_fotos, peso_gramos, longitud_cm, altura_cm, ancho_cm)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (producto_id) DO NOTHING
                """,
                [
                    (
                        f["producto_id"], f.get("categoria_nombre"),
                        f.get("longitud_nombre"), f.get("longitud_descripcion"),
                        f.get("cantidad_fotos"), f.get("peso_gramos"),
                        f.get("longitud_cm"), f.get("altura_cm"), f.get("ancho_cm"),
                    )
                    for f in filas
                ],
            )
    return len(filas)


def upsert_pedidos(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.pedidos
                    (pedido_id, cliente_id, estado_pedido, fecha_compra,
                     fecha_aprobacion, fecha_entrega_transportista,
                     fecha_entrega_cliente, fecha_estimada_entrega, banderas_calidad)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (pedido_id) DO NOTHING
                """,
                [
                    (
                        f["pedido_id"], f["cliente_id"], f["estado_pedido"],
                        f["fecha_compra"], f.get("fecha_aprobacion"),
                        f.get("fecha_entrega_transportista"), f.get("fecha_entrega_cliente"),
                        f["fecha_estimada_entrega"],
                        json.dumps(f.get("banderas_calidad", {})),
                    )
                    for f in filas
                ],
            )
    return len(filas)


def upsert_items(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.items_pedido
                    (pedido_id, numero_item, producto_id, vendedor_id,
                     fecha_limite_despacho, precio, valor_flete)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pedido_id, numero_item) DO NOTHING
                """,
                [
                    (
                        f["pedido_id"], f["numero_item"], f["producto_id"], f["vendedor_id"],
                        f["fecha_limite_despacho"], f["precio"], f["valor_flete"],
                    )
                    for f in filas
                ],
            )
    return len(filas)


def upsert_pagos(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.pagos_pedido
                    (pedido_id, secuencia_pago, tipo_pago, cuotas_pago, monto_pago)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (pedido_id, secuencia_pago) DO NOTHING
                """,
                [
                    (f["pedido_id"], f["secuencia_pago"], f["tipo_pago"],
                     f["cuotas_pago"], f["monto_pago"])
                    for f in filas
                ],
            )
    return len(filas)


def upsert_resenas(conn: Connection, filas: list[dict[str, Any]]) -> int:
    if not filas:
        return 0
    with conn.pipeline():
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO operativo.resenas_pedido
                    (resena_id, pedido_id, puntaje, titulo_comentario,
                     mensaje_comentario, fecha_creacion, fecha_respuesta)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (resena_id, pedido_id) DO NOTHING
                """,
                [
                    (
                        f["resena_id"], f["pedido_id"], f["puntaje"],
                        f.get("titulo_comentario"), f.get("mensaje_comentario"),
                        f["fecha_creacion"], f["fecha_respuesta"],
                    )
                    for f in filas
                ],
            )
    return len(filas)


# ---------------------------------------------------------------------------
# Consultas auxiliares (usadas en pruebas e informes)
# ---------------------------------------------------------------------------

def contar_tabla(conn: Connection, schema: str, tabla: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {schema}.{tabla}").fetchone()  # noqa: S608
    return int(row[0]) if row else 0


def contar_rechazados(conn: Connection, carga_id: uuid.UUID) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM calidad.registros_rechazados WHERE carga_id = %s",
        (carga_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def obtener_cargas_con_banderas(conn: Connection, flag_key: str) -> list[dict]:
    rows = conn.execute(
        "SELECT pedido_id, banderas_calidad FROM operativo.pedidos WHERE banderas_calidad ? %s",
        (flag_key,),
    ).fetchall()
    return [{"pedido_id": r[0], "banderas_calidad": r[1]} for r in rows]
