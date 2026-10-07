"""tests/test_ingesta.py — Pruebas de la ingesta ETL sobre opsledger_test.

Cada prueba arranca con la base limpia (downgrade base → upgrade head)
y usa exclusivamente TEST_DATABASE_URL.  Nunca toca la base de desarrollo.
"""
from __future__ import annotations

import io
import os
import sys
import textwrap
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Cargar .env antes de cualquier import de src.*
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _c = _line.strip()
        if _c and not _c.startswith("#") and "=" in _c:
            _k, _v = _c.split("=", 1)
            _k = _k.strip()
            if _k not in os.environ:
                os.environ[_k] = _v.strip().strip('"').strip("'")

import alembic.command
import alembic.config

from src.core.config import get_test_database_url
from src.modules.ingesta import repository as repo
from src.modules.ingesta import service


# ---------------------------------------------------------------------------
# Helpers de conexión a la base de pruebas
# ---------------------------------------------------------------------------

def _get_test_dsn() -> str:
    url = get_test_database_url()
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    if not db_name.endswith("_test"):
        raise ValueError(
            f"TEST_DATABASE_URL apunta a '{db_name}'. "
            "La base de pruebas DEBE terminar en '_test'."
        )
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def _get_test_url() -> str:
    return get_test_database_url()


def _reset_db() -> None:
    """Downgrade base → upgrade head en opsledger_test."""
    url = _get_test_url()
    alembic_cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    alembic.command.downgrade(alembic_cfg, "base")
    alembic.command.upgrade(alembic_cfg, "head")


def _conn() -> psycopg.Connection:
    return psycopg.connect(_get_test_dsn(), autocommit=False, connect_timeout=10)


# ---------------------------------------------------------------------------
# Datos mínimos reutilizables
# ---------------------------------------------------------------------------

CAT_OK = [{"categoria_nombre_portugues": "cat_a", "categoria_nombre_ingles": "cat_a_en"}]
CLIENTE_OK = [{
    "cliente_id": "cli-001", "cliente_unico_id": "uni-001",
    "codigo_postal_prefijo": "01310", "ciudad": "São Paulo", "estado_region": "SP",
}]
VENDEDOR_OK = [{
    "vendedor_id": "ven-001", "codigo_postal_prefijo": "01310",
    "ciudad": "São Paulo", "estado_region": "SP",
}]
PRODUCTO_OK = [{
    "producto_id": "prod-001", "categoria_nombre": "cat_a",
    "longitud_nombre": 10, "longitud_descripcion": 50, "cantidad_fotos": 2,
    "peso_gramos": 300, "longitud_cm": 20, "altura_cm": 10, "ancho_cm": 15,
}]
PEDIDO_OK = {
    "pedido_id": "ped-001", "cliente_id": "cli-001", "estado_pedido": "delivered",
    "fecha_compra": "2018-01-01 10:00:00", "fecha_aprobacion": "2018-01-01 11:00:00",
    "fecha_entrega_transportista": "2018-01-02 08:00:00",
    "fecha_entrega_cliente": "2018-01-05 14:00:00",
    "fecha_estimada_entrega": "2018-01-10 00:00:00",
}
ITEM_OK = {
    "pedido_id": "ped-001", "numero_item": "1", "producto_id": "prod-001",
    "vendedor_id": "ven-001", "fecha_limite_despacho": "2018-01-03 00:00:00",
    "precio": "99.90", "valor_flete": "12.50",
}
PAGO_OK = {
    "pedido_id": "ped-001", "secuencia_pago": "1", "tipo_pago": "credit_card",
    "cuotas_pago": "1", "monto_pago": "99.90",
}
RESENA_OK = {
    "resena_id": "res-001", "pedido_id": "ped-001", "puntaje": "5",
    "titulo_comentario": "", "mensaje_comentario": "",
    "fecha_creacion": "2018-01-06 00:00:00", "fecha_respuesta": "2018-01-07 00:00:00",
}


def _seed_base(conn: psycopg.Connection) -> None:
    """Inserta cliente, vendedor, categoría y producto base."""
    repo.upsert_categorias(conn, CAT_OK)
    repo.upsert_clientes(conn, CLIENTE_OK)
    repo.upsert_vendedores(conn, VENDEDOR_OK)
    repo.upsert_productos(conn, PRODUCTO_OK)
    conn.commit()


def _seed_pedido(conn: psycopg.Connection) -> None:
    accepted, _ = service.transformar_pedidos([PEDIDO_OK], uuid.uuid4())
    repo.upsert_pedidos(conn, accepted)
    conn.commit()


# ---------------------------------------------------------------------------
# Fixture: CSV temporal escrito en disco
# ---------------------------------------------------------------------------

def _write_csv(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


# ===========================================================================
# PRUEBA 0 — Categoría sin traducción al inglés (blando)
# ===========================================================================

def test_categoria_sin_traduccion_se_inserta_con_ingles_nulo():
    _reset_db()
    with _conn() as conn:
        filas = [{"categoria_nombre_portugues": "pc_gamer", "categoria_nombre_ingles": None}]
        service.transformar_categorias(filas, uuid.uuid4())
        repo.upsert_categorias(conn, [{"categoria_nombre_portugues": "pc_gamer", "categoria_nombre_ingles": None}])
        conn.commit()
        row = conn.execute(
            "SELECT categoria_nombre_ingles FROM operativo.categorias_producto WHERE categoria_nombre_portugues = 'pc_gamer'"
        ).fetchone()
    assert row is not None
    assert row[0] is None


# ===========================================================================
# PRUEBA 1 — Producto sin categoría existente → inserta categoría con ingles=NULL
# ===========================================================================

def test_producto_inserta_categoria_faltante_dentro_de_transaccion():
    _reset_db()
    with _conn() as conn:
        # Solo existe cat_a; el producto referencia "cat_nueva"
        repo.upsert_categorias(conn, CAT_OK)
        conn.commit()
        cats_existentes = service.obtener_categorias_existentes(conn)
        aceptadas, _, cats_nuevas = service.transformar_productos(
            [{"producto_id": "p1", "categoria_nombre": "cat_nueva",
              "longitud_nombre": "10", "longitud_descripcion": "50",
              "cantidad_fotos": "1", "peso_gramos": "200",
              "longitud_cm": "10", "altura_cm": "5", "ancho_cm": "8"}],
            uuid.uuid4(),
            cats_existentes,
        )
        # Dentro de transacción: insertar cat faltante y luego producto
        with conn.transaction():
            repo.upsert_categorias(conn, cats_nuevas)
            repo.upsert_productos(conn, aceptadas)

        row = conn.execute(
            "SELECT categoria_nombre_ingles FROM operativo.categorias_producto WHERE categoria_nombre_portugues = 'cat_nueva'"
        ).fetchone()
        assert row is not None
        assert row[0] is None
        prod = conn.execute(
            "SELECT producto_id FROM operativo.productos WHERE producto_id = 'p1'"
        ).fetchone()
        assert prod is not None


# ===========================================================================
# PRUEBA 2 — NOT NULL duro en campo obligatorio
# ===========================================================================

def test_not_null_duro_cliente_id():
    _reset_db()
    filas = [{
        "cliente_id": "",  # vacío → None
        "cliente_unico_id": "uni-x",
        "codigo_postal_prefijo": "01310",
        "ciudad": "SP",
        "estado_region": "SP",
    }]
    aceptadas, rechazadas = service.transformar_clientes(filas, uuid.uuid4())
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "cliente_id" in rechazadas[0]["motivo"]


# ===========================================================================
# PRUEBA 3 — CHECK violado: estado_pedido inválido
# ===========================================================================

def test_check_estado_pedido_invalido_es_error_duro():
    _reset_db()
    filas = [{**PEDIDO_OK, "estado_pedido": "ENVIADO"}]  # estado inválido
    aceptadas, rechazadas = service.transformar_pedidos(filas, uuid.uuid4())
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "estado_pedido" in rechazadas[0]["motivo"].lower()


# ===========================================================================
# PRUEBA 4 — CHECK violado: puntaje de reseña fuera de [1,5]
# ===========================================================================

def test_check_puntaje_fuera_de_rango_es_error_duro():
    _reset_db()
    filas = [{**RESENA_OK, "puntaje": "6"}]
    aceptadas, rechazadas = service.transformar_resenas(filas, uuid.uuid4())
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "puntaje" in rechazadas[0]["motivo"]


# ===========================================================================
# PRUEBA 5 — CHECK violado: precio negativo en ítem
# ===========================================================================

def test_check_precio_negativo_es_error_duro():
    _reset_db()
    filas = [{**ITEM_OK, "precio": "-5.00"}]
    aceptadas, rechazadas = service.transformar_items(filas, uuid.uuid4())
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "precio" in rechazadas[0]["motivo"]


# ===========================================================================
# PRUEBA 6 — Valor no convertible a entero es error duro
# ===========================================================================

def test_valor_no_convertible_a_entero_es_error_duro():
    _reset_db()
    filas = [{
        "producto_id": "p-err", "categoria_nombre": "cat_a",
        "longitud_nombre": "CIEN",  # no convertible
        "longitud_descripcion": "50", "cantidad_fotos": "1",
        "peso_gramos": "300", "longitud_cm": "10", "altura_cm": "5", "ancho_cm": "8",
    }]
    cats = {"cat_a"}
    aceptadas, rechazadas, _ = service.transformar_productos(filas, uuid.uuid4(), cats)
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "longitud_nombre" in rechazadas[0]["motivo"]


# ===========================================================================
# PRUEBA 7 — Valor no convertible a decimal es error duro
# ===========================================================================

def test_valor_no_convertible_a_decimal_es_error_duro():
    _reset_db()
    filas = [{**ITEM_OK, "precio": "noventa"}]
    aceptadas, rechazadas = service.transformar_items(filas, uuid.uuid4())
    assert len(aceptadas) == 0
    assert len(rechazadas) == 1
    assert "precio" in rechazadas[0]["motivo"]


# ===========================================================================
# PRUEBA 8 — Clave duplicada en el mismo archivo (conserva primera, rechaza resto)
# ===========================================================================

def test_clave_duplicada_en_archivo_conserva_primera_rechaza_resto():
    _reset_db()
    filas = [
        {"cliente_id": "dup-001", "cliente_unico_id": "u1", "codigo_postal_prefijo": "01310", "ciudad": "SP", "estado_region": "SP"},
        {"cliente_id": "dup-001", "cliente_unico_id": "u2", "codigo_postal_prefijo": "01311", "ciudad": "RJ", "estado_region": "RJ"},
        {"cliente_id": "dup-001", "cliente_unico_id": "u3", "codigo_postal_prefijo": "01312", "ciudad": "MG", "estado_region": "MG"},
    ]
    aceptadas, rechazadas = service.transformar_clientes(filas, uuid.uuid4())
    assert len(aceptadas) == 1
    assert aceptadas[0]["cliente_unico_id"] == "u1"
    assert len(rechazadas) == 2
    assert all("duplicada" in r["motivo"].lower() for r in rechazadas)


# ===========================================================================
# PRUEBA 9 — FK inexistente va a registros_rechazados
# ===========================================================================

def test_fk_inexistente_va_a_registros_rechazados():
    """Ítem con pedido_id que no existe → FK viola al hacer INSERT → rechazo registrado."""
    _reset_db()
    with _conn() as conn:
        _seed_base(conn)
        # No creamos pedido → FK de items apuntará a nada

        carga_id = repo.registrar_carga(conn, "test_fk.csv", "fk-hash-001", 1)
        conn.commit()

        filas_raw = [{**ITEM_OK, "pedido_id": "ped-NOEXISTE"}]
        aceptadas, _ = service.transformar_items(filas_raw, carga_id)
        # La transformación acepta (no puede verificar FK en Python).
        # Intentamos insertar; la FK falla dentro de un savepoint para no romper la conexión.
        fk_error: Exception | None = None
        try:
            with conn.transaction():
                try:
                    with conn.transaction():   # savepoint interno
                        repo.upsert_items(conn, aceptadas)
                except Exception as exc:
                    fk_error = exc   # La FK violada se captura aquí
        except Exception:
            pass  # El savepoint hizo rollback al bloque exterior; conexión OK

        assert fk_error is not None, "Debería haber fallado la FK"

        # Registrar el rechazo manualmente (como haría _cargar_archivo en except)
        repo.insertar_rechazo(conn, carga_id, 1, "operativo.items_pedido", str(fk_error), filas_raw[0])
        conn.commit()

        n = repo.contar_rechazados(conn, carga_id)
    assert n >= 1


# ===========================================================================
# PRUEBA 10 — Bandera sin_fecha_entrega_cliente
# ===========================================================================

def test_bandera_sin_fecha_entrega_cliente():
    _reset_db()
    fila = {**PEDIDO_OK, "fecha_entrega_cliente": ""}  # vacío → None
    aceptadas, rechazadas = service.transformar_pedidos([fila], uuid.uuid4())
    assert len(rechazadas) == 0
    assert len(aceptadas) == 1
    assert aceptadas[0]["banderas_calidad"].get(service.FLAG_SIN_FECHA_ENTREGA_CLIENTE) is True


# ===========================================================================
# PRUEBA 11 — Bandera sin_fecha_aprobacion
# ===========================================================================

def test_bandera_sin_fecha_aprobacion():
    _reset_db()
    fila = {**PEDIDO_OK, "fecha_aprobacion": ""}
    aceptadas, _ = service.transformar_pedidos([fila], uuid.uuid4())
    assert aceptadas[0]["banderas_calidad"].get(service.FLAG_SIN_FECHA_APROBACION) is True


# ===========================================================================
# PRUEBA 12 — Bandera despacho_antes_de_aprobacion
# ===========================================================================

def test_bandera_despacho_antes_de_aprobacion():
    _reset_db()
    fila = {
        **PEDIDO_OK,
        "fecha_aprobacion": "2018-01-02 12:00:00",
        "fecha_entrega_transportista": "2018-01-01 08:00:00",  # antes de aprobación
    }
    aceptadas, _ = service.transformar_pedidos([fila], uuid.uuid4())
    assert aceptadas[0]["banderas_calidad"].get(service.FLAG_DESPACHO_ANTES_DE_APROBACION) is True


# ===========================================================================
# PRUEBA 13 — Bandera entrega_cliente_antes_de_transportista
# ===========================================================================

def test_bandera_entrega_cliente_antes_de_transportista():
    _reset_db()
    fila = {
        **PEDIDO_OK,
        "fecha_entrega_transportista": "2018-01-05 14:00:00",
        "fecha_entrega_cliente": "2018-01-04 10:00:00",  # antes del transportista
    }
    aceptadas, _ = service.transformar_pedidos([fila], uuid.uuid4())
    assert aceptadas[0]["banderas_calidad"].get(service.FLAG_ENTREGA_CLIENTE_ANTES_DE_TRANSPORTISTA) is True


# ===========================================================================
# PRUEBA 14 — Bandera no_delivered_con_fecha_entrega
# ===========================================================================

def test_bandera_no_delivered_con_fecha_entrega():
    _reset_db()
    fila = {
        **PEDIDO_OK,
        "estado_pedido": "shipped",
        "fecha_entrega_cliente": "2018-01-05 14:00:00",
    }
    aceptadas, _ = service.transformar_pedidos([fila], uuid.uuid4())
    assert aceptadas[0]["banderas_calidad"].get(service.FLAG_NO_DELIVERED_CON_FECHA_ENTREGA) is True


# ===========================================================================
# PRUEBA 15 — Idempotencia: segunda carga del mismo archivo no duplica filas
# ===========================================================================

def test_idempotencia_segunda_carga_no_duplica(tmp_path: Path):
    _reset_db()
    csv = _write_csv(tmp_path, "olist_customers_dataset.csv",
        "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\n"
        "idem-001,uni-idem,01310,São Paulo,SP\n"
    )
    url = _get_test_url()
    service.ejecutar_ingesta(tmp_path, db_url=url)
    service.ejecutar_ingesta(tmp_path, db_url=url)  # segunda ejecución
    with _conn() as conn:
        n = repo.contar_tabla(conn, "operativo", "clientes")
    assert n == 1


# ===========================================================================
# PRUEBA 16 — Segunda ejecución reporta "ya procesado"
# ===========================================================================

def test_segunda_ejecucion_reporta_ya_procesado(tmp_path: Path, capsys):
    _reset_db()
    csv = _write_csv(tmp_path, "olist_customers_dataset.csv",
        "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\n"
        "skip-001,uni-skip,01310,São Paulo,SP\n"
    )
    url = _get_test_url()
    service.ejecutar_ingesta(tmp_path, db_url=url)
    service.ejecutar_ingesta(tmp_path, db_url=url)
    captured = capsys.readouterr()
    assert "ya procesado" in captured.out or "[OMITIDO]" in captured.out


# ===========================================================================
# PRUEBA 17 — Rollback: fallo a mitad de carga deja operativo sin cambios
# ===========================================================================

def test_rollback_deja_operativo_sin_cambios():
    """Simula un fallo en medio de la inserción de ítems y verifica que
    operativo.items_pedido quede vacío después del rollback."""
    _reset_db()
    with _conn() as conn:
        _seed_base(conn)
        _seed_pedido(conn)

        n_antes = repo.contar_tabla(conn, "operativo", "items_pedido")
        carga_id = repo.registrar_carga(conn, "fail.csv", "rollback-hash-001", 1)
        conn.commit()

        # Intentamos insertar un ítem válido y luego forzamos un error dentro
        # de la misma transacción (savepoint); conn.transaction() hace rollback
        # automáticamente al salir por excepción.
        try:
            with conn.transaction():
                repo.upsert_items(conn, [{
                    "pedido_id": "ped-001", "numero_item": 99,
                    "producto_id": "prod-001", "vendedor_id": "ven-001",
                    "fecha_limite_despacho": "2018-01-03 00:00:00",
                    "precio": Decimal("10.00"), "valor_flete": Decimal("1.00"),
                }])
                # Forzar error dentro de la transacción
                conn.execute("SELECT 1/0")
        except Exception:
            pass  # El context manager ya hizo rollback del savepoint/bloque

        n_despues = repo.contar_tabla(conn, "operativo", "items_pedido")
    assert n_despues == n_antes
