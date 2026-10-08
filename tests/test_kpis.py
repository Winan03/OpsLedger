"""tests/test_kpis.py — Pruebas unitarias y de integración para la capa de KPIs y Analytics.

Ejecuta sobre opsledger_test y nunca toca la base de desarrollo.
"""
from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import alembic.command
import alembic.config
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

from src.core.config import get_test_database_url
from src.modules.ingesta import repository as repo_ingesta
from src.modules.kpis import repository as repo_kpis
from src.modules.kpis import service as srv_kpis
from src.modules.kpis.config import SeveridadAlerta, UmbralKPI
from src.modules.kpis.repository import FiltrosKPI


def _get_test_dsn() -> str:
    url = get_test_database_url()
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")
    if not db_name.endswith("_test"):
        raise ValueError(f"TEST_DATABASE_URL apunta a '{db_name}', debe terminar en '_test'.")
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def _reset_db() -> None:
    alembic_cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", get_test_database_url())
    alembic.command.downgrade(alembic_cfg, "base")
    alembic.command.upgrade(alembic_cfg, "head")


def _conn() -> psycopg.Connection:
    return psycopg.connect(_get_test_dsn(), autocommit=False, connect_timeout=10)


# ---------------------------------------------------------------------------
# Seed de datos sintéticos controlados
# ---------------------------------------------------------------------------

def _seed_synthetic_dataset(conn: psycopg.Connection) -> None:
    """Inserta dataset pequeño con valores matemáticamente conocidos."""
    # 1. Categorías
    cats = [
        {"categoria_nombre_portugues": "electronica", "categoria_nombre_ingles": "electronics"},
        {"categoria_nombre_portugues": "moda", "categoria_nombre_ingles": "fashion"},
    ]
    repo_ingesta.upsert_categorias(conn, cats)

    # 2. Clientes
    clientes = [
        {"cliente_id": "c1", "cliente_unico_id": "u1", "codigo_postal_prefijo": "01000", "ciudad": "Sao Paulo", "estado_region": "SP"},
        {"cliente_id": "c2", "cliente_unico_id": "u2", "codigo_postal_prefijo": "20000", "ciudad": "Rio de Janeiro", "estado_region": "RJ"},
        {"cliente_id": "c3", "cliente_unico_id": "u3", "codigo_postal_prefijo": "30000", "ciudad": "Belo Horizonte", "estado_region": "MG"},
    ]
    repo_ingesta.upsert_clientes(conn, clientes)

    # 3. Vendedores
    vendedores = [
        {"vendedor_id": "v1", "codigo_postal_prefijo": "01000", "ciudad": "Sao Paulo", "estado_region": "SP"},
        {"vendedor_id": "v2", "codigo_postal_prefijo": "80000", "ciudad": "Curitiba", "estado_region": "PR"},
    ]
    repo_ingesta.upsert_vendedores(conn, vendedores)

    # 4. Productos
    productos = [
        {"producto_id": "p_elec", "categoria_nombre": "electronica", "longitud_nombre": 10, "longitud_descripcion": 50, "cantidad_fotos": 1, "peso_gramos": 500, "longitud_cm": 20, "altura_cm": 10, "ancho_cm": 15},
        {"producto_id": "p_moda", "categoria_nombre": "moda", "longitud_nombre": 10, "longitud_descripcion": 50, "cantidad_fotos": 1, "peso_gramos": 200, "longitud_cm": 20, "altura_cm": 5, "ancho_cm": 15},
        {"producto_id": "p_sincat", "categoria_nombre": None, "longitud_nombre": 10, "longitud_descripcion": 50, "cantidad_fotos": 1, "peso_gramos": 300, "longitud_cm": 10, "altura_cm": 5, "ancho_cm": 10},
    ]
    repo_ingesta.upsert_productos(conn, productos)

    # 5. Pedidos con métricas conocidas
    # Pedido 1 (SP): Compra 2018-01-01 10:00 -> Aprob 2018-01-01 12:00 -> Transp 2018-01-03 12:00 (2d) -> Entrega 2018-01-06 10:00 (5d ciclo) -> Est 2018-01-10 (A tiempo, -4d)
    # Pedido 2 (RJ): Compra 2018-01-02 10:00 -> Aprob 2018-01-02 10:00 -> Transp 2018-01-06 10:00 (4d) -> Entrega 2018-01-17 10:00 (15d ciclo) -> Est 2018-01-15 (Tarde, +2d)
    # Pedido 3 (MG): Cancelado
    pedidos = [
        {
            "pedido_id": "ped-1", "cliente_id": "c1", "estado_pedido": "delivered",
            "fecha_compra": "2018-01-01 10:00:00", "fecha_aprobacion": "2018-01-01 12:00:00",
            "fecha_entrega_transportista": "2018-01-03 12:00:00", "fecha_entrega_cliente": "2018-01-06 10:00:00",
            "fecha_estimada_entrega": "2018-01-10 00:00:00", "banderas_calidad": {},
        },
        {
            "pedido_id": "ped-2", "cliente_id": "c2", "estado_pedido": "delivered",
            "fecha_compra": "2018-01-02 10:00:00", "fecha_aprobacion": "2018-01-02 10:00:00",
            "fecha_entrega_transportista": "2018-01-06 10:00:00", "fecha_entrega_cliente": "2018-01-17 10:00:00",
            "fecha_estimada_entrega": "2018-01-15 00:00:00", "banderas_calidad": {},
        },
        {
            "pedido_id": "ped-3", "cliente_id": "c3", "estado_pedido": "canceled",
            "fecha_compra": "2018-01-05 10:00:00", "fecha_aprobacion": "2018-01-05 11:00:00",
            "fecha_entrega_transportista": None, "fecha_entrega_cliente": None,
            "fecha_estimada_entrega": "2018-01-20 00:00:00", "banderas_calidad": {},
        },
    ]
    repo_ingesta.upsert_pedidos(conn, pedidos)

    # 6. Items: ped-1 tiene 3 ítems (2 de electrónica, 1 de moda) para probar la regla anti-duplicación
    items = [
        {"pedido_id": "ped-1", "numero_item": 1, "producto_id": "p_elec", "vendedor_id": "v1", "fecha_limite_despacho": "2018-01-05", "precio": Decimal("100.00"), "valor_flete": Decimal("10.00")},
        {"pedido_id": "ped-1", "numero_item": 2, "producto_id": "p_elec", "vendedor_id": "v1", "fecha_limite_despacho": "2018-01-05", "precio": Decimal("100.00"), "valor_flete": Decimal("10.00")},
        {"pedido_id": "ped-1", "numero_item": 3, "producto_id": "p_moda", "vendedor_id": "v2", "fecha_limite_despacho": "2018-01-05", "precio": Decimal("50.00"), "valor_flete": Decimal("5.00")},
        {"pedido_id": "ped-2", "numero_item": 1, "producto_id": "p_sincat", "vendedor_id": "v2", "fecha_limite_despacho": "2018-01-08", "precio": Decimal("200.00"), "valor_flete": Decimal("30.00")},
    ]
    repo_ingesta.upsert_items(conn, items)

    # 7. Reseñas
    resenas = [
        {"resena_id": "r1", "pedido_id": "ped-1", "puntaje": 5, "titulo_comentario": "Excelente", "mensaje_comentario": "Llegó rápido", "fecha_creacion": "2018-01-07 00:00:00", "fecha_respuesta": "2018-01-08 00:00:00"},
        {"resena_id": "r2", "pedido_id": "ped-2", "puntaje": 2, "titulo_comentario": "Tarde", "mensaje_comentario": "Demoró mucho", "fecha_creacion": "2018-01-18 00:00:00", "fecha_respuesta": "2018-01-19 00:00:00"},
    ]
    repo_ingesta.upsert_resenas(conn, resenas)
    conn.commit()


# ===========================================================================
# PRUEBAS DE REGLA ANTI-MULTIPLICACIÓN (EXISTS vs JOIN)
# ===========================================================================

def test_regla_anti_multiplicacion_kpi_otd_con_pedido_multi_item():
    """Un pedido con 3 ítems no debe ser contado 3 veces al filtrar por categoría."""
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)

        # Filtramos por categoría 'electronica'
        # El ped-1 tiene 2 ítems de electrónica. Si se usara JOIN, contaría 2 pedidos entregados.
        # Con EXISTS, debe contar exactamente 1 pedido entregado y 100% OTD.
        filtros = FiltrosKPI(categoria_nombre="electronica")
        res = repo_kpis.consultar_kpi2_otd(conn, filtros)

        assert res["total_pedidos_entregados"] == 1, "EXISTS debe contar exactamente 1 pedido aunque tenga 2 items de electronica"
        assert res["entregados_a_tiempo"] == 1
        assert res["otd_pct"] == 100.0


def test_regla_anti_multiplicacion_kpi_tiempo_ciclo():
    """Tiempo de ciclo sobre pedido multi-ítem con filtro de categoría."""
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)

        filtros = FiltrosKPI(categoria_nombre="electronica")
        res = repo_kpis.consultar_kpi1_tiempo_ciclo(conn, filtros)

        assert res["total_pedidos"] == 1
        assert res["tiempo_ciclo_medio_dias"] == 5.0  # (2018-01-06 10:00 - 2018-01-01 10:00 = 5 días)


# ===========================================================================
# PRUEBAS DE LOS 8 KPIS CON VALORES CONOCIDOS
# ===========================================================================

def test_kpi1_tiempo_ciclo_global():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi1_tiempo_ciclo(conn)
        # ped-1 = 5 días, ped-2 = 15 días -> media = 10.0 días
        assert res["total_pedidos"] == 2
        assert res["tiempo_ciclo_medio_dias"] == 10.0
        assert res["min_dias"] == 5.0
        assert res["max_dias"] == 15.0


def test_kpi2_otd_global():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi2_otd(conn)
        # ped-1 = a tiempo, ped-2 = tarde -> 1 de 2 = 50.0%
        assert res["total_pedidos_entregados"] == 2
        assert res["entregados_a_tiempo"] == 1
        assert res["entregados_tarde"] == 1
        assert res["otd_pct"] == 50.0


def test_kpi3_desviacion_plazo_global():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi3_desviacion_plazo(conn)
        assert res["total_pedidos"] == 2
        assert res["total_pedidos_tardios"] == 1
        assert res["retraso_medio_tardios_dias"] > 0


def test_kpi4_despacho_vendedor():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi4_despacho_vendedor(conn)
        # ped-1: 2018-01-03 12:00 - 2018-01-01 12:00 = 2.0 días
        # ped-2: 2018-01-06 10:00 - 2018-01-02 10:00 = 4.0 días
        # media = 3.0 días
        assert res["total_pedidos_evaluados"] == 2
        assert res["despacho_medio_dias"] == 3.0


def test_kpi5_costo_logistico_relativo():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi5_costo_logistico(conn)
        # Productos: 100 + 100 + 50 + 200 = 450.00
        # Flete: 10 + 10 + 5 + 30 = 55.00
        # Pct: 55 / 450 * 100 = 12.22%
        assert res["valor_total_productos"] == 450.00
        assert res["valor_total_flete"] == 55.00
        assert res["costo_logistico_relativo_pct"] == 12.22


def test_kpi6_ventas_brutas_e_ingresos_realizados():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi6_ingresos_y_ticket(conn)
        # ped-1 = 250 prod + 25 flete = 275 total
        # ped-2 = 200 prod + 30 flete = 230 total
        # Ventas brutas = 275 + 230 = 505.00
        # Ingresos realizados (delivered) = 505.00
        # Ticket promedio = 505 / 2 = 252.50
        assert res["total_pedidos_facturados"] == 2
        assert res["ventas_brutas_totales"] == 505.00
        assert res["ingresos_realizados_totales"] == 505.00
        assert res["ticket_promedio_total"] == 252.50


def test_kpi5_y_kpi6_comparten_definicion_ventas_brutas_excluyendo_unavailable():
    """Verifica que un pedido 'unavailable' con ítems queda excluido tanto del KPI 5 como del KPI 6."""
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        # Insertamos un pedido unavailable CON items
        repo_ingesta.upsert_pedidos(conn, [{
            "pedido_id": "ped-unav", "cliente_id": "c1", "estado_pedido": "unavailable",
            "fecha_compra": "2018-01-03 10:00:00", "fecha_aprobacion": "2018-01-03 11:00:00",
            "fecha_entrega_transportista": None, "fecha_entrega_cliente": None,
            "fecha_estimada_entrega": "2018-01-20 00:00:00", "banderas_calidad": {},
        }])
        repo_ingesta.upsert_items(conn, [{
            "pedido_id": "ped-unav", "numero_item": 1, "producto_id": "p_elec",
            "vendedor_id": "v1", "fecha_limite_despacho": "2018-01-08",
            "precio": Decimal("999.00"), "valor_flete": Decimal("100.00"),
        }])
        conn.commit()

        res_kpi5 = repo_kpis.consultar_kpi5_costo_logistico(conn)
        res_kpi6 = repo_kpis.consultar_kpi6_ingresos_y_ticket(conn)

        # Ambos deben ignorar ped-unav (R$ 999 prod + R$ 100 flete)
        assert res_kpi5["valor_total_productos"] == 450.00
        assert res_kpi5["valor_total_flete"] == 55.00
        assert res_kpi5["total_pedidos"] == 2

        assert res_kpi6["total_pedidos_facturados"] == 2
        assert res_kpi6["ventas_brutas_totales"] == 505.00


def test_kpi7_tasa_cancelacion():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi7_tasa_cancelacion(conn)
        # 3 pedidos totales, 1 cancelado -> 33.33%
        assert res["total_pedidos"] == 3
        assert res["pedidos_cancelados"] == 1
        assert res["tasa_cancelacion_pct"] == 33.33


def test_kpi8_satisfaccion_vs_retraso():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        res = repo_kpis.consultar_kpi8_satisfaccion_retraso(conn)
        # r1 (a tiempo) = 5.0, r2 (con retraso) = 2.0 -> media = 3.5
        assert res["total_resenas"] == 2
        assert res["csat_promedio_global"] == 3.5
        assert res["csat_a_tiempo"] == 5.0
        assert res["csat_con_retraso"] == 2.0


# ===========================================================================
# PRUEBAS DE FILTROS (SIN CATEGORÍA, REGIÓN Y FECHAS)
# ===========================================================================

def test_filtro_sin_categoria():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        filtros = FiltrosKPI(categoria_nombre="sin_categoria")
        res = repo_kpis.consultar_kpi2_otd(conn, filtros)
        # Solo ped-2 tiene producto sin categoría (tarde)
        assert res["total_pedidos_entregados"] == 1
        assert res["entregados_a_tiempo"] == 0
        assert res["otd_pct"] == 0.0


def test_filtro_por_region():
    _reset_db()
    with _conn() as conn:
        _seed_synthetic_dataset(conn)
        # SP tiene ped-1 (5d ciclo, a tiempo)
        filtros = FiltrosKPI(estados_region=["SP"])
        res = repo_kpis.consultar_kpi1_tiempo_ciclo(conn, filtros)
        assert res["total_pedidos"] == 1
        assert res["tiempo_ciclo_medio_dias"] == 5.0


# ===========================================================================
# PRUEBAS DE EVALUACIÓN DE ALERTAS CON MIN_N
# ===========================================================================

def test_alerta_no_dispara_si_no_alcanza_min_n():
    """Si OTD es 50% pero min_n es 50 y solo hay 2 pedidos, NO debe disparar alerta."""
    umbrales = [
        UmbralKPI(
            kpi_id="kpi_2_otd",
            nombre="OTD Bajo",
            operador="<",
            valor_referencia=90.0,
            severidad=SeveridadAlerta.ADVERTENCIA,
            min_n=50,
            mensaje_plantilla="OTD {valor:.2f}% bajo (N={n})",
        )
    ]
    alertas = srv_kpis.evaluar_alertas("kpi_2_otd", valor_actual=50.0, n_muestra=2, umbrales=umbrales)
    assert len(alertas) == 0, "No debe disparar si N < min_n"


def test_alerta_dispara_si_supera_min_n():
    """Si OTD es 50% y N >= min_n, debe disparar con severidad correcta."""
    umbrales = [
        UmbralKPI(
            kpi_id="kpi_2_otd",
            nombre="OTD Bajo",
            operador="<",
            valor_referencia=90.0,
            severidad=SeveridadAlerta.ADVERTENCIA,
            min_n=50,
            mensaje_plantilla="OTD {valor:.2f}% bajo (N={n})",
        )
    ]
    alertas = srv_kpis.evaluar_alertas("kpi_2_otd", valor_actual=50.0, n_muestra=100, umbrales=umbrales)
    assert len(alertas) == 1
    assert alertas[0].severidad == SeveridadAlerta.ADVERTENCIA
    assert alertas[0].valor_actual == 50.0
