"""service.py — Orquestador ETL de ingesta de archivos CSV.

Flujo por archivo:
  1. SHA-256 → ¿ya completado? → skip
  2. Registrar carga en 'procesando'
  3. Leer CSV todo como texto (vacíos → None)
  4. COPY a staging
  5. Validar y transformar tipos
  6. En una sola transacción:
     a. Pre-insertar categorías faltantes (solo en carga de productos)
     b. INSERT ON CONFLICT a operativo
     c. INSERT rechazos a calidad.registros_rechazados
     d. UPDATE cargas_archivos → 'completado'
     e. DELETE staging WHERE carga_id = …
  7. Si falla: rollback, UPDATE → 'fallido' (staging se conserva)
  8. Guardar informe JSON en reports/calidad/
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from src.core.config import get_database_url
from src.modules.ingesta import repository as repo

# Banderas de calidad — nombres canónicos según docs/modelo_datos.md
FLAG_SIN_FECHA_ENTREGA_CLIENTE = "sin_fecha_entrega_cliente"
FLAG_SIN_FECHA_APROBACION = "sin_fecha_aprobacion"
FLAG_DESPACHO_ANTES_DE_APROBACION = "despacho_antes_de_aprobacion"
FLAG_ENTREGA_CLIENTE_ANTES_DE_TRANSPORTISTA = "entrega_cliente_antes_de_transportista"
FLAG_NO_DELIVERED_CON_FECHA_ENTREGA = "no_delivered_con_fecha_entrega"

ESTADOS_PEDIDO_VALIDOS = frozenset(
    {"delivered", "shipped", "canceled", "unavailable", "invoiced", "processing", "created", "approved"}
)

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports" / "calidad"


# ---------------------------------------------------------------------------
# Helpers de conversión estricta
# ---------------------------------------------------------------------------

def _strip(val: Any) -> str | None:
    """Recorta espacios; cadena vacía → None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _to_int(val: Any, campo: str) -> tuple[int | None, str | None]:
    """Convierte a int.  None si era vacío/None.  Devuelve (valor, motivo_error)."""
    s = _strip(val)
    if s is None:
        return None, None
    try:
        return int(float(s)), None  # float permite "610.0" → 610
    except (ValueError, TypeError):
        return None, f"Valor no convertible a entero en '{campo}': {val!r}"


def _to_decimal(val: Any, campo: str) -> tuple[Decimal | None, str | None]:
    s = _strip(val)
    if s is None:
        return None, None
    try:
        return Decimal(s), None
    except (InvalidOperation, TypeError):
        return None, f"Valor no convertible a decimal en '{campo}': {val!r}"


def _to_datetime(val: Any, campo: str) -> tuple[datetime | None, str | None]:
    s = _strip(val)
    if s is None:
        return None, None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt), None
        except ValueError:
            pass
    return None, f"Valor no convertible a fecha en '{campo}': {val!r}"


# ---------------------------------------------------------------------------
# SHA-256
# ---------------------------------------------------------------------------

def calcular_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Lectura CSV
# ---------------------------------------------------------------------------

def leer_csv_como_texto(path: Path, rename: dict[str, str]) -> list[dict[str, str | None]]:
    """Lee el CSV completo como texto.  Vacíos → None.  Renombra columnas según rename."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.rename(columns=rename)
    # Vacíos → None
    df = df.where(df != "", other=None)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Validación y transformación por tabla
# ---------------------------------------------------------------------------

def _validar_no_nulo(valor: Any, campo: str) -> str | None:
    """Devuelve motivo de error si el campo es None o vacío."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return f"Campo obligatorio nulo o vacío: '{campo}'"
    return None


def transformar_categorias(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    """Devuelve (aceptadas, rechazadas)."""
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[str] = set()

    for i, f in enumerate(filas_raw, start=1):
        nombre = _strip(f.get("categoria_nombre_portugues"))
        ingles = _strip(f.get("categoria_nombre_ingles"))

        motivo = _validar_no_nulo(nombre, "categoria_nombre_portugues")
        if motivo:
            rechazadas.append({"numero_fila": i, "motivo": motivo, "datos_crudos": f})
            continue

        # Duplicado en el mismo archivo: se conserva la primera
        if nombre in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: categoria_nombre_portugues='{nombre}'",
                "datos_crudos": f,
            })
            continue
        seen.add(nombre)

        aceptadas.append({"categoria_nombre_portugues": nombre, "categoria_nombre_ingles": ingles})
    return aceptadas, rechazadas


def transformar_clientes(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[str] = set()

    for i, f in enumerate(filas_raw, start=1):
        cliente_id = _strip(f.get("cliente_id"))
        cliente_unico_id = _strip(f.get("cliente_unico_id"))
        # código postal se guarda como texto (puede tener ceros a la izquierda)
        codigo_postal = _strip(f.get("codigo_postal_prefijo"))
        ciudad = _strip(f.get("ciudad"))
        estado = _strip(f.get("estado_region"))

        errores = []
        for val, campo in [
            (cliente_id, "cliente_id"),
            (cliente_unico_id, "cliente_unico_id"),
            (codigo_postal, "codigo_postal_prefijo"),
            (ciudad, "ciudad"),
            (estado, "estado_region"),
        ]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)

        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        if cliente_id in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: cliente_id='{cliente_id}'",
                "datos_crudos": f,
            })
            continue
        seen.add(cliente_id)

        aceptadas.append({
            "cliente_id": cliente_id,
            "cliente_unico_id": cliente_unico_id,
            "codigo_postal_prefijo": codigo_postal,
            "ciudad": ciudad,
            "estado_region": estado,
        })
    return aceptadas, rechazadas


def transformar_vendedores(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[str] = set()

    for i, f in enumerate(filas_raw, start=1):
        vendedor_id = _strip(f.get("vendedor_id"))
        codigo_postal = _strip(f.get("codigo_postal_prefijo"))
        ciudad = _strip(f.get("ciudad"))
        estado = _strip(f.get("estado_region"))

        errores = []
        for val, campo in [
            (vendedor_id, "vendedor_id"),
            (codigo_postal, "codigo_postal_prefijo"),
            (ciudad, "ciudad"),
            (estado, "estado_region"),
        ]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)

        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        if vendedor_id in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: vendedor_id='{vendedor_id}'",
                "datos_crudos": f,
            })
            continue
        seen.add(vendedor_id)

        aceptadas.append({
            "vendedor_id": vendedor_id,
            "codigo_postal_prefijo": codigo_postal,
            "ciudad": ciudad,
            "estado_region": estado,
        })
    return aceptadas, rechazadas


def transformar_productos(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
    categorias_existentes: set[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Devuelve (aceptadas, rechazadas, categorias_faltantes).

    categorias_faltantes: categorías que aparecen en productos pero no en
    categorias_producto; deben insertarse con ingles=NULL antes de los productos.
    """
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    cats_faltantes: dict[str, None] = {}
    seen: set[str] = set()

    for i, f in enumerate(filas_raw, start=1):
        producto_id = _strip(f.get("producto_id"))
        categoria = _strip(f.get("categoria_nombre"))

        m = _validar_no_nulo(producto_id, "producto_id")
        if m:
            rechazadas.append({"numero_fila": i, "motivo": m, "datos_crudos": f})
            continue

        if producto_id in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: producto_id='{producto_id}'",
                "datos_crudos": f,
            })
            continue
        seen.add(producto_id)

        # Conversiones estrictas de enteros (blando si nulo; duro si no convertible)
        longitud_nombre, e1 = _to_int(f.get("longitud_nombre"), "longitud_nombre")
        longitud_desc, e2 = _to_int(f.get("longitud_descripcion"), "longitud_descripcion")
        cantidad_fotos, e3 = _to_int(f.get("cantidad_fotos"), "cantidad_fotos")
        peso, e4 = _to_int(f.get("peso_gramos"), "peso_gramos")
        longitud_cm, e5 = _to_int(f.get("longitud_cm"), "longitud_cm")
        altura_cm, e6 = _to_int(f.get("altura_cm"), "altura_cm")
        ancho_cm, e7 = _to_int(f.get("ancho_cm"), "ancho_cm")

        errores_conversion = [e for e in [e1, e2, e3, e4, e5, e6, e7] if e]
        if errores_conversion:
            rechazadas.append({
                "numero_fila": i,
                "motivo": "; ".join(errores_conversion),
                "datos_crudos": f,
            })
            continue

        # Categoría: si no existe en operativo, la agregamos con ingles=NULL (blando)
        if categoria and categoria not in categorias_existentes:
            cats_faltantes[categoria] = None

        aceptadas.append({
            "producto_id": producto_id,
            "categoria_nombre": categoria,
            "longitud_nombre": longitud_nombre,
            "longitud_descripcion": longitud_desc,
            "cantidad_fotos": cantidad_fotos,
            "peso_gramos": peso,
            "longitud_cm": longitud_cm,
            "altura_cm": altura_cm,
            "ancho_cm": ancho_cm,
        })

    cats_nuevas = [
        {"categoria_nombre_portugues": k, "categoria_nombre_ingles": None}
        for k in cats_faltantes
    ]
    return aceptadas, rechazadas, cats_nuevas


def transformar_pedidos(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[str] = set()

    for i, f in enumerate(filas_raw, start=1):
        pedido_id = _strip(f.get("pedido_id"))
        cliente_id = _strip(f.get("cliente_id"))
        estado = _strip(f.get("estado_pedido"))

        # NOT NULL duros
        errores = []
        for val, campo in [(pedido_id, "pedido_id"), (cliente_id, "cliente_id"), (estado, "estado_pedido")]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)

        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        # CHECK estado_pedido
        if estado not in ESTADOS_PEDIDO_VALIDOS:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Valor inválido en estado_pedido: '{estado}'",
                "datos_crudos": f,
            })
            continue

        # Duplicado en el mismo archivo
        if pedido_id in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: pedido_id='{pedido_id}'",
                "datos_crudos": f,
            })
            continue
        seen.add(pedido_id)

        # Fechas — fecha_compra y fecha_estimada son NOT NULL
        fecha_compra, e1 = _to_datetime(f.get("fecha_compra"), "fecha_compra")
        fecha_estimada, e2 = _to_datetime(f.get("fecha_estimada_entrega"), "fecha_estimada_entrega")

        errores_fecha = [e for e in [e1, e2] if e]
        if errores_fecha:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores_fecha), "datos_crudos": f})
            continue

        m1 = _validar_no_nulo(fecha_compra, "fecha_compra")
        m2 = _validar_no_nulo(fecha_estimada, "fecha_estimada_entrega")
        if m1 or m2:
            rechazadas.append({
                "numero_fila": i,
                "motivo": "; ".join(m for m in [m1, m2] if m),
                "datos_crudos": f,
            })
            continue

        # Fechas opcionales (no convertible = error duro)
        fecha_aprobacion, ea = _to_datetime(f.get("fecha_aprobacion"), "fecha_aprobacion")
        fecha_transportista, et = _to_datetime(f.get("fecha_entrega_transportista"), "fecha_entrega_transportista")
        fecha_cliente, ec = _to_datetime(f.get("fecha_entrega_cliente"), "fecha_entrega_cliente")

        errores_opt = [e for e in [ea, et, ec] if e]
        if errores_opt:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores_opt), "datos_crudos": f})
            continue

        # Banderas de calidad (blandas)
        banderas: dict[str, bool] = {}

        if estado == "delivered" and fecha_cliente is None:
            banderas[FLAG_SIN_FECHA_ENTREGA_CLIENTE] = True

        if estado == "delivered" and fecha_aprobacion is None:
            banderas[FLAG_SIN_FECHA_APROBACION] = True

        if fecha_transportista and fecha_aprobacion and fecha_transportista < fecha_aprobacion:
            banderas[FLAG_DESPACHO_ANTES_DE_APROBACION] = True

        if fecha_cliente and fecha_transportista and fecha_cliente < fecha_transportista:
            banderas[FLAG_ENTREGA_CLIENTE_ANTES_DE_TRANSPORTISTA] = True

        if estado != "delivered" and fecha_cliente is not None:
            banderas[FLAG_NO_DELIVERED_CON_FECHA_ENTREGA] = True

        aceptadas.append({
            "pedido_id": pedido_id,
            "cliente_id": cliente_id,
            "estado_pedido": estado,
            "fecha_compra": fecha_compra,
            "fecha_aprobacion": fecha_aprobacion,
            "fecha_entrega_transportista": fecha_transportista,
            "fecha_entrega_cliente": fecha_cliente,
            "fecha_estimada_entrega": fecha_estimada,
            "banderas_calidad": banderas,
        })
    return aceptadas, rechazadas


def transformar_items(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[tuple] = set()

    for i, f in enumerate(filas_raw, start=1):
        pedido_id = _strip(f.get("pedido_id"))
        producto_id = _strip(f.get("producto_id"))
        vendedor_id = _strip(f.get("vendedor_id"))

        errores = []
        for val, campo in [
            (pedido_id, "pedido_id"),
            (producto_id, "producto_id"),
            (vendedor_id, "vendedor_id"),
        ]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)

        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        numero_item, e1 = _to_int(f.get("numero_item"), "numero_item")
        precio, e2 = _to_decimal(f.get("precio"), "precio")
        valor_flete, e3 = _to_decimal(f.get("valor_flete"), "valor_flete")
        fecha_despacho, e4 = _to_datetime(f.get("fecha_limite_despacho"), "fecha_limite_despacho")

        conv_errors = [e for e in [e1, e2, e3, e4] if e]
        if conv_errors:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(conv_errors), "datos_crudos": f})
            continue

        errores_nulos = []
        for val, campo in [
            (numero_item, "numero_item"),
            (precio, "precio"),
            (valor_flete, "valor_flete"),
            (fecha_despacho, "fecha_limite_despacho"),
        ]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores_nulos.append(m)
        if errores_nulos:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores_nulos), "datos_crudos": f})
            continue

        # CHECK precio y flete >= 0
        if precio < Decimal("0"):
            rechazadas.append({"numero_fila": i, "motivo": f"precio no puede ser negativo: {precio}", "datos_crudos": f})
            continue
        if valor_flete < Decimal("0"):
            rechazadas.append({"numero_fila": i, "motivo": f"valor_flete no puede ser negativo: {valor_flete}", "datos_crudos": f})
            continue

        pk = (pedido_id, numero_item)
        if pk in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: (pedido_id, numero_item)={pk}",
                "datos_crudos": f,
            })
            continue
        seen.add(pk)

        aceptadas.append({
            "pedido_id": pedido_id,
            "numero_item": numero_item,
            "producto_id": producto_id,
            "vendedor_id": vendedor_id,
            "fecha_limite_despacho": fecha_despacho,
            "precio": precio,
            "valor_flete": valor_flete,
        })
    return aceptadas, rechazadas


def transformar_pagos(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[tuple] = set()

    for i, f in enumerate(filas_raw, start=1):
        pedido_id = _strip(f.get("pedido_id"))
        tipo_pago = _strip(f.get("tipo_pago"))

        errores = []
        for val, campo in [(pedido_id, "pedido_id"), (tipo_pago, "tipo_pago")]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)

        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        secuencia, e1 = _to_int(f.get("secuencia_pago"), "secuencia_pago")
        cuotas, e2 = _to_int(f.get("cuotas_pago"), "cuotas_pago")
        monto, e3 = _to_decimal(f.get("monto_pago"), "monto_pago")

        conv_errors = [e for e in [e1, e2, e3] if e]
        if conv_errors:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(conv_errors), "datos_crudos": f})
            continue

        errores_nulos = []
        for val, campo in [(secuencia, "secuencia_pago"), (monto, "monto_pago")]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores_nulos.append(m)
        if errores_nulos:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores_nulos), "datos_crudos": f})
            continue

        if monto < Decimal("0"):
            rechazadas.append({"numero_fila": i, "motivo": f"monto_pago no puede ser negativo: {monto}", "datos_crudos": f})
            continue

        cuotas = cuotas if cuotas is not None else 1

        pk = (pedido_id, secuencia)
        if pk in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: (pedido_id, secuencia_pago)={pk}",
                "datos_crudos": f,
            })
            continue
        seen.add(pk)

        aceptadas.append({
            "pedido_id": pedido_id,
            "secuencia_pago": secuencia,
            "tipo_pago": tipo_pago,
            "cuotas_pago": cuotas,
            "monto_pago": monto,
        })
    return aceptadas, rechazadas


def transformar_resenas(
    filas_raw: list[dict],
    carga_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    aceptadas: list[dict] = []
    rechazadas: list[dict] = []
    seen: set[tuple] = set()

    for i, f in enumerate(filas_raw, start=1):
        resena_id = _strip(f.get("resena_id"))
        pedido_id = _strip(f.get("pedido_id"))

        errores = []
        for val, campo in [(resena_id, "resena_id"), (pedido_id, "pedido_id")]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores.append(m)
        if errores:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores), "datos_crudos": f})
            continue

        puntaje, ep = _to_int(f.get("puntaje"), "puntaje")
        fecha_creacion, ef = _to_datetime(f.get("fecha_creacion"), "fecha_creacion")
        fecha_respuesta, er = _to_datetime(f.get("fecha_respuesta"), "fecha_respuesta")

        conv_errors = [e for e in [ep, ef, er] if e]
        if conv_errors:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(conv_errors), "datos_crudos": f})
            continue

        errores_nulos = []
        for val, campo in [
            (puntaje, "puntaje"),
            (fecha_creacion, "fecha_creacion"),
            (fecha_respuesta, "fecha_respuesta"),
        ]:
            m = _validar_no_nulo(val, campo)
            if m:
                errores_nulos.append(m)
        if errores_nulos:
            rechazadas.append({"numero_fila": i, "motivo": "; ".join(errores_nulos), "datos_crudos": f})
            continue

        # CHECK puntaje 1-5
        if not (1 <= puntaje <= 5):
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"puntaje fuera de rango [1,5]: {puntaje}",
                "datos_crudos": f,
            })
            continue

        pk = (resena_id, pedido_id)
        if pk in seen:
            rechazadas.append({
                "numero_fila": i,
                "motivo": f"Clave duplicada en el archivo: (resena_id, pedido_id)={pk}",
                "datos_crudos": f,
            })
            continue
        seen.add(pk)

        aceptadas.append({
            "resena_id": resena_id,
            "pedido_id": pedido_id,
            "puntaje": puntaje,
            "titulo_comentario": _strip(f.get("titulo_comentario")),
            "mensaje_comentario": _strip(f.get("mensaje_comentario")),
            "fecha_creacion": fecha_creacion,
            "fecha_respuesta": fecha_respuesta,
        })
    return aceptadas, rechazadas


# ---------------------------------------------------------------------------
# Informe de calidad
# ---------------------------------------------------------------------------

def guardar_informe(
    nombre_archivo: str,
    carga_id: uuid.UUID,
    leidos: int,
    aceptados: int,
    rechazados: int,
    con_bandera: int,
    rechazos_detalle: list[dict],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(nombre_archivo).stem
    out = REPORTS_DIR / f"{stem}_{carga_id}.json"
    informe = {
        "archivo": nombre_archivo,
        "carga_id": str(carga_id),
        "generado_en": datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
        "leidos": leidos,
        "aceptados": aceptados,
        "rechazados": rechazados,
        "con_bandera_calidad": con_bandera,
        "rechazos": rechazos_detalle,
    }
    out.write_text(json.dumps(informe, indent=2, default=str), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Función pública de categorías cargadas (usada en transformar_productos)
# ---------------------------------------------------------------------------

def obtener_categorias_existentes(conn) -> set[str]:
    rows = conn.execute("SELECT categoria_nombre_portugues FROM operativo.categorias_producto").fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def _cargar_archivo(
    conn,
    csv_path: Path,
    staging_table: str,
    staging_cols: list[str],
    rename_map: dict[str, str],
    transformar_fn,
    upsert_fn,
    tabla_operativo: str,
    extra_kwargs: dict | None = None,
) -> dict:
    """Carga un CSV en staging → operativo.  Devuelve métricas."""
    nombre = csv_path.name
    sha = calcular_sha256(csv_path)

    if repo.existe_carga_completada(conn, sha):
        print(f"  [OMITIDO] {nombre}: ya procesado (hash conocido).")
        return {"ya_procesado": True, "nombre": nombre}

    filas_raw = leer_csv_como_texto(csv_path, rename_map)
    total = len(filas_raw)

    carga_id = repo.registrar_carga(conn, nombre, sha, total)
    conn.commit()  # Persiste el 'procesando' fuera de la transacción de datos

    try:
        # COPY a staging
        repo.copy_to_staging(conn, staging_table, staging_cols, filas_raw, carga_id)
        conn.commit()

        # Transformación
        kwargs = {"carga_id": carga_id}
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        if staging_table == "stg_productos":
            # Necesita conocer las categorías ya cargadas
            cats_existentes = obtener_categorias_existentes(conn)
            aceptadas, rechazadas, cats_nuevas = transformar_fn(filas_raw, carga_id, cats_existentes)
        else:
            aceptadas, rechazadas = transformar_fn(filas_raw, carga_id)
            cats_nuevas = []

        # ---- Transacción atómica ----
        with conn.transaction():
            # Pre-insertar categorías faltantes (solo en productos)
            if cats_nuevas:
                repo.upsert_categorias(conn, cats_nuevas)

            con_bandera = 0
            # Insertar aceptadas
            if tabla_operativo == "pedidos":
                for row in aceptadas:
                    if row.get("banderas_calidad"):
                        con_bandera += 1
            upsert_fn(conn, aceptadas)

            # Registrar rechazados
            for r in rechazadas:
                repo.insertar_rechazo(
                    conn, carga_id, r["numero_fila"],
                    f"operativo.{tabla_operativo}", r["motivo"], r["datos_crudos"],
                )

            repo.marcar_completado(conn, carga_id, len(aceptadas), len(rechazadas))
            repo.limpiar_staging(conn, staging_table, carga_id)
        # ---- Fin transacción ----

    except Exception as exc:
        conn.rollback()
        repo.marcar_fallido(conn, carga_id, str(exc))
        conn.commit()
        raise

    aceptados_n = len(aceptadas)
    rechazados_n = len(rechazadas)

    # Imprimir resumen
    cats_info = f" (+{len(cats_nuevas)} categorias nuevas)" if cats_nuevas else ""
    print(
        f"  [OK] {nombre}: leidos={total}  aceptados={aceptados_n}"
        f"  rechazados={rechazados_n}  con_bandera={con_bandera}{cats_info}"
    )

    # Informe JSON
    rechazos_detalle = [
        {"fila": r["numero_fila"], "motivo": r["motivo"]} for r in rechazadas
    ]
    informe_path = guardar_informe(nombre, carga_id, total, aceptados_n, rechazados_n, con_bandera, rechazos_detalle)

    return {
        "ya_procesado": False,
        "nombre": nombre,
        "carga_id": str(carga_id),
        "leidos": total,
        "aceptados": aceptados_n,
        "rechazados": rechazados_n,
        "con_bandera": con_bandera,
        "informe": str(informe_path),
    }


# Mapeos CSV → columnas operativo
_RENAME_CATEGORIAS = {
    "product_category_name": "categoria_nombre_portugues",
    "product_category_name_english": "categoria_nombre_ingles",
}
_RENAME_CLIENTES = {
    "customer_id": "cliente_id",
    "customer_unique_id": "cliente_unico_id",
    "customer_zip_code_prefix": "codigo_postal_prefijo",
    "customer_city": "ciudad",
    "customer_state": "estado_region",
}
_RENAME_VENDEDORES = {
    "seller_id": "vendedor_id",
    "seller_zip_code_prefix": "codigo_postal_prefijo",
    "seller_city": "ciudad",
    "seller_state": "estado_region",
}
_RENAME_PRODUCTOS = {
    "product_id": "producto_id",
    "product_category_name": "categoria_nombre",
    "product_name_lenght": "longitud_nombre",
    "product_description_lenght": "longitud_descripcion",
    "product_photos_qty": "cantidad_fotos",
    "product_weight_g": "peso_gramos",
    "product_length_cm": "longitud_cm",
    "product_height_cm": "altura_cm",
    "product_width_cm": "ancho_cm",
}
_RENAME_PEDIDOS = {
    "order_id": "pedido_id",
    "customer_id": "cliente_id",
    "order_status": "estado_pedido",
    "order_purchase_timestamp": "fecha_compra",
    "order_approved_at": "fecha_aprobacion",
    "order_delivered_carrier_date": "fecha_entrega_transportista",
    "order_delivered_customer_date": "fecha_entrega_cliente",
    "order_estimated_delivery_date": "fecha_estimada_entrega",
}
_RENAME_ITEMS = {
    "order_id": "pedido_id",
    "order_item_id": "numero_item",
    "product_id": "producto_id",
    "seller_id": "vendedor_id",
    "shipping_limit_date": "fecha_limite_despacho",
    "price": "precio",
    "freight_value": "valor_flete",
}
_RENAME_PAGOS = {
    "order_id": "pedido_id",
    "payment_sequential": "secuencia_pago",
    "payment_type": "tipo_pago",
    "payment_installments": "cuotas_pago",
    "payment_value": "monto_pago",
}
_RENAME_RESENAS = {
    "review_id": "resena_id",
    "order_id": "pedido_id",
    "review_score": "puntaje",
    "review_comment_title": "titulo_comentario",
    "review_comment_message": "mensaje_comentario",
    "review_creation_date": "fecha_creacion",
    "review_answer_timestamp": "fecha_respuesta",
}


def _normalizar_dsn(url: str) -> str:
    """Convierte postgresql+psycopg:// → postgresql:// para psycopg.connect()."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def ejecutar_ingesta(data_dir: Path, db_url: str | None = None) -> list[dict]:
    """Punto de entrada principal.  Carga todos los CSV en orden de FK."""
    raw_url = db_url or get_database_url()
    dsn = _normalizar_dsn(raw_url)
    results: list[dict] = []

    with psycopg.connect(dsn, autocommit=False, connect_timeout=10) as conn:
        # Al iniciar, marcar huérfanos 'procesando' como fallidos
        n_limpiados = repo.limpiar_cargas_procesando(conn)
        conn.commit()
        if n_limpiados:
            print(f"[AVISO] Se marcaron {n_limpiados} cargas antiguas 'procesando' como 'fallido'.")

        archivos = [
            # (nombre_csv, staging_table, staging_cols, rename_map, transformar_fn, upsert_fn, tabla_op)
            (
                "product_category_name_translation.csv",
                "stg_categorias_traduccion",
                ["categoria_nombre_portugues", "categoria_nombre_ingles"],
                _RENAME_CATEGORIAS,
                transformar_categorias,
                repo.upsert_categorias,
                "categorias_producto",
            ),
            (
                "olist_customers_dataset.csv",
                "stg_clientes",
                ["cliente_id", "cliente_unico_id", "codigo_postal_prefijo", "ciudad", "estado_region"],
                _RENAME_CLIENTES,
                transformar_clientes,
                repo.upsert_clientes,
                "clientes",
            ),
            (
                "olist_sellers_dataset.csv",
                "stg_vendedores",
                ["vendedor_id", "codigo_postal_prefijo", "ciudad", "estado_region"],
                _RENAME_VENDEDORES,
                transformar_vendedores,
                repo.upsert_vendedores,
                "vendedores",
            ),
            (
                "olist_products_dataset.csv",
                "stg_productos",
                ["producto_id", "categoria_nombre", "longitud_nombre", "longitud_descripcion",
                 "cantidad_fotos", "peso_gramos", "longitud_cm", "altura_cm", "ancho_cm"],
                _RENAME_PRODUCTOS,
                transformar_productos,
                repo.upsert_productos,
                "productos",
            ),
            (
                "olist_orders_dataset.csv",
                "stg_pedidos",
                ["pedido_id", "cliente_id", "estado_pedido", "fecha_compra",
                 "fecha_aprobacion", "fecha_entrega_transportista",
                 "fecha_entrega_cliente", "fecha_estimada_entrega"],
                _RENAME_PEDIDOS,
                transformar_pedidos,
                repo.upsert_pedidos,
                "pedidos",
            ),
            (
                "olist_order_items_dataset.csv",
                "stg_items_pedido",
                ["pedido_id", "numero_item", "producto_id", "vendedor_id",
                 "fecha_limite_despacho", "precio", "valor_flete"],
                _RENAME_ITEMS,
                transformar_items,
                repo.upsert_items,
                "items_pedido",
            ),
            (
                "olist_order_payments_dataset.csv",
                "stg_pagos_pedido",
                ["pedido_id", "secuencia_pago", "tipo_pago", "cuotas_pago", "monto_pago"],
                _RENAME_PAGOS,
                transformar_pagos,
                repo.upsert_pagos,
                "pagos_pedido",
            ),
            (
                "olist_order_reviews_dataset.csv",
                "stg_resenas_pedido",
                ["resena_id", "pedido_id", "puntaje", "titulo_comentario",
                 "mensaje_comentario", "fecha_creacion", "fecha_respuesta"],
                _RENAME_RESENAS,
                transformar_resenas,
                repo.upsert_resenas,
                "resenas_pedido",
            ),
        ]

        for entry in archivos:
            nombre_csv, staging_table, staging_cols, rename_map, transformar_fn, upsert_fn, tabla_op = entry
            csv_path = data_dir / nombre_csv
            if not csv_path.exists():
                print(f"  [AVISO] {nombre_csv}: archivo no encontrado, omitiendo.")
                continue

            result = _cargar_archivo(
                conn=conn,
                csv_path=csv_path,
                staging_table=staging_table,
                staging_cols=staging_cols,
                rename_map=rename_map,
                transformar_fn=transformar_fn,
                upsert_fn=upsert_fn,
                tabla_operativo=tabla_op,
            )
            results.append(result)

    return results
