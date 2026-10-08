"""service.py — Servicio de cálculo, consolidación y evaluación de alertas de KPIs.

Coordina las consultas al repositorio, calcula variaciones y evalúa los umbrales
de alerta considerando el tamaño de muestra mínimo (min_n).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from psycopg import Connection

from src.core.config import get_database_url
from src.modules.ingesta.service import _normalizar_dsn
from src.modules.kpis import repository as repo
from src.modules.kpis.config import UMBRALES_POR_DEFECTO, SeveridadAlerta, UmbralKPI
from src.modules.kpis.repository import FiltrosKPI


@dataclass
class AlertaDisparada:
    kpi_id: str
    nombre: str
    severidad: SeveridadAlerta
    valor_actual: float
    valor_referencia: float
    tamano_muestra: int
    mensaje: str


def evaluar_alertas(
    kpi_id: str,
    valor_actual: float,
    n_muestra: int,
    umbrales: list[UmbralKPI] | None = None,
) -> list[AlertaDisparada]:
    """Evalúa si un valor infringe alguno de los umbrales configurados con N >= min_n."""
    umbrales = umbrales or UMBRALES_POR_DEFECTO
    alertas: list[AlertaDisparada] = []

    for u in umbrales:
        if u.kpi_id != kpi_id:
            continue
        if n_muestra < u.min_n:
            continue  # Ignorar si no alcanza la muestra mínima

        dispara = False
        if u.operador == ">" and valor_actual > u.valor_referencia:
            dispara = True
        elif u.operador == ">=" and valor_actual >= u.valor_referencia:
            dispara = True
        elif u.operador == "<" and valor_actual < u.valor_referencia:
            dispara = True
        elif u.operador == "<=" and valor_actual <= u.valor_referencia:
            dispara = True

        if dispara:
            msg = u.mensaje_plantilla.format(
                valor=valor_actual,
                referencia=u.valor_referencia,
                n=n_muestra,
            )
            alertas.append(
                AlertaDisparada(
                    kpi_id=u.kpi_id,
                    nombre=u.nombre,
                    severidad=u.severidad,
                    valor_actual=valor_actual,
                    valor_referencia=u.valor_referencia,
                    tamano_muestra=n_muestra,
                    mensaje=msg,
                )
            )

    return alertas


def obtener_resumen_completo_kpis(
    conn: Connection,
    filtros: FiltrosKPI | None = None,
    umbrales: list[UmbralKPI] | None = None,
) -> dict[str, Any]:
    """Calcula los 8 KPIs consolidados y evalúa todas las alertas aplicables."""
    filtros = filtros or FiltrosKPI()

    kpi1 = repo.consultar_kpi1_tiempo_ciclo(conn, filtros)
    kpi2 = repo.consultar_kpi2_otd(conn, filtros)
    kpi3 = repo.consultar_kpi3_desviacion_plazo(conn, filtros)
    kpi4 = repo.consultar_kpi4_despacho_vendedor(conn, filtros)
    kpi5 = repo.consultar_kpi5_costo_logistico(conn, filtros)
    kpi6 = repo.consultar_kpi6_ingresos_y_ticket(conn, filtros)
    kpi7 = repo.consultar_kpi7_tasa_cancelacion(conn, filtros)
    kpi8 = repo.consultar_kpi8_satisfaccion_retraso(conn, filtros)

    # Evaluación de alertas
    todas_alertas: list[AlertaDisparada] = []
    todas_alertas.extend(
        evaluar_alertas("kpi_1_tiempo_ciclo", kpi1["tiempo_ciclo_medio_dias"], kpi1["total_pedidos"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_2_otd", kpi2["otd_pct"], kpi2["total_pedidos_entregados"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_3_retraso_tardios", kpi3["retraso_medio_tardios_dias"], kpi3["total_pedidos_tardios"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_4_despacho_vendedor", kpi4["despacho_medio_dias"], kpi4["total_pedidos_evaluados"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_5_costo_logistico_relativo", kpi5["costo_logistico_relativo_pct"], kpi5["total_pedidos"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_7_tasa_cancelacion", kpi7["tasa_cancelacion_pct"], kpi7["total_pedidos"], umbrales)
    )
    todas_alertas.extend(
        evaluar_alertas("kpi_8_csat_global", kpi8["csat_promedio_global"], kpi8["total_resenas"], umbrales)
    )

    return {
        "kpi_1_tiempo_ciclo": kpi1,
        "kpi_2_otd": kpi2,
        "kpi_3_desviacion_plazo": kpi3,
        "kpi_4_despacho_vendedor": kpi4,
        "kpi_5_costo_logistico": kpi5,
        "kpi_6_ingresos_y_ticket": kpi6,
        "kpi_7_tasa_cancelacion": kpi7,
        "kpi_8_satisfaccion_retraso": kpi8,
        "alertas": [asdict(a) for a in todas_alertas],
        "total_alertas": len(todas_alertas),
    }
