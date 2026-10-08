"""config.py — Configuración y umbrales de alerta ilustrativos para KPIs.

Cada umbral define la condición matemática, la severidad (ADVERTENCIA o CRITICO)
y el tamaño de muestra mínimo (min_n) requerido para evitar falsos positivos
en periodos o cohortes con bajo volumen muestral.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SeveridadAlerta(str, Enum):
    INFO = "INFO"
    ADVERTENCIA = "ADVERTENCIA"
    CRITICO = "CRITICO"


@dataclass(frozen=True)
class UmbralKPI:
    kpi_id: str
    nombre: str
    operador: str  # '>', '<', '>=', '<='
    valor_referencia: float
    severidad: SeveridadAlerta
    min_n: int
    mensaje_plantilla: str


# Umbrales calibrados empíricamente según la distribución histórica real (2017-2018)
# Nota: Son valores ilustrativos de referencia para el dashboard/alertas, ajustables según la política de negocio.
UMBRALES_POR_DEFECTO: list[UmbralKPI] = [
    # KPI 1: Tiempo de ciclo (Histórico semanal: P50=11.8d, P75=14.0d, P90=15.5d)
    UmbralKPI(
        kpi_id="kpi_1_tiempo_ciclo",
        nombre="Tiempo de Ciclo Elevado",
        operador=">",
        valor_referencia=14.5,  # ~P80 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=30,
        mensaje_plantilla="El tiempo de ciclo medio ({valor:.2f} días) supera el umbral de advertencia de {referencia:.1f} días (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_1_tiempo_ciclo",
        nombre="Tiempo de Ciclo Crítico",
        operador=">",
        valor_referencia=16.0,  # ~P92 histórico semanal
        severidad=SeveridadAlerta.CRITICO,
        min_n=30,
        mensaje_plantilla="El tiempo de ciclo medio ({valor:.2f} días) se encuentra en nivel crítico superando los {referencia:.1f} días (N={n}).",
    ),
    # KPI 2: OTD (Cumplimiento de entrega - Histórico semanal: P50=95.0%, P10=83.6%, P5=80.0%)
    UmbralKPI(
        kpi_id="kpi_2_otd",
        nombre="OTD Bajo",
        operador="<",
        valor_referencia=85.0,  # ~P12 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=50,
        mensaje_plantilla="El cumplimiento de entrega ({valor:.2f}%) cayó por debajo del SLA objetivo del {referencia:.1f}% (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_2_otd",
        nombre="OTD Crítico",
        operador="<",
        valor_referencia=80.0,  # ~P5 histórico semanal
        severidad=SeveridadAlerta.CRITICO,
        min_n=50,
        mensaje_plantilla="El cumplimiento de entrega ({valor:.2f}%) cayó a nivel crítico por debajo del {referencia:.1f}% (N={n}).",
    ),
    # KPI 3: Desviación de plazo en tardíos (Histórico semanal: P50=8.77d, P75=11.98d, P90=15.11d)
    UmbralKPI(
        kpi_id="kpi_3_retraso_tardios",
        nombre="Retraso Severo en Pedidos Tardíos",
        operador=">",
        valor_referencia=12.0,  # P75 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=20,
        mensaje_plantilla="La demora media en pedidos tardíos ({valor:.2f} días) supera el P75 histórico de {referencia:.1f} días (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_3_retraso_tardios",
        nombre="Retraso Crítico en Pedidos Tardíos",
        operador=">",
        valor_referencia=15.0,  # P90 histórico semanal (15.11 d)
        severidad=SeveridadAlerta.CRITICO,
        min_n=20,
        mensaje_plantilla="La demora media en pedidos tardíos ({valor:.2f} días) alcanza nivel crítico superando el P90 de {referencia:.1f} días (N={n}).",
    ),
    # KPI 4: Tiempo de despacho del vendedor (Histórico semanal: P50=2.81d, P75=3.07d, P90=3.30d)
    UmbralKPI(
        kpi_id="kpi_4_despacho_vendedor",
        nombre="Despacho Lento del Vendedor",
        operador=">",
        valor_referencia=3.3,  # P90 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=25,
        mensaje_plantilla="El tiempo de despacho medio ({valor:.2f} días) supera el P90 de {referencia:.1f} días (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_4_despacho_vendedor",
        nombre="Despacho Crítico del Vendedor",
        operador=">",
        valor_referencia=4.0,  # >P95 histórico semanal (3.55 d)
        severidad=SeveridadAlerta.CRITICO,
        min_n=25,
        mensaje_plantilla="El tiempo de despacho medio ({valor:.2f} días) alcanza nivel crítico (> {referencia:.1f} días, N={n}).",
    ),
    # KPI 5: Costo logístico relativo (Histórico semanal: P50=16.49%, P75=17.56%, P90=18.02%)
    UmbralKPI(
        kpi_id="kpi_5_costo_logistico_relativo",
        nombre="Flete Relativo Elevado",
        operador=">",
        valor_referencia=18.0,  # P90 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=30,
        mensaje_plantilla="El flete representa el {valor:.2f}% del valor de productos, superando el límite del {referencia:.1f}%.",
    ),
    UmbralKPI(
        kpi_id="kpi_5_costo_logistico_relativo",
        nombre="Flete Relativo Crítico",
        operador=">",
        valor_referencia=20.0,  # >P95 histórico semanal (18.54%)
        severidad=SeveridadAlerta.CRITICO,
        min_n=30,
        mensaje_plantilla="El flete representa el {valor:.2f}% del valor de productos, alcanzando nivel crítico (> {referencia:.1f}%).",
    ),
    # KPI 7: Tasa de cancelación (Histórico mensual: P50=0.53%, P75=0.76%, P90=1.10%)
    UmbralKPI(
        kpi_id="kpi_7_tasa_cancelacion",
        nombre="Tasa de Cancelación Elevada",
        operador=">",
        valor_referencia=1.0,  # ~P85 histórico mensual
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=50,
        mensaje_plantilla="La tasa de cancelación ({valor:.2f}%) supera el umbral de advertencia del {referencia:.1f}% (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_7_tasa_cancelacion",
        nombre="Tasa de Cancelación Crítica",
        operador=">",
        valor_referencia=1.5,  # >P95 histórico mensual (1.23%)
        severidad=SeveridadAlerta.CRITICO,
        min_n=50,
        mensaje_plantilla="La tasa de cancelación ({valor:.2f}%) alcanza nivel crítico (> {referencia:.1f}%, N={n}).",
    ),
    # KPI 8: Satisfacción (CSAT - Histórico semanal: P50=4.14, P10=3.90, P5=3.76)
    UmbralKPI(
        kpi_id="kpi_8_csat_global",
        nombre="CSAT Promedio Bajo",
        operador="<",
        valor_referencia=3.9,  # P10 histórico semanal
        severidad=SeveridadAlerta.ADVERTENCIA,
        min_n=30,
        mensaje_plantilla="La satisfacción media ({valor:.2f}/5.0) cayó por debajo del estándar de {referencia:.1f} (N={n}).",
    ),
    UmbralKPI(
        kpi_id="kpi_8_csat_global",
        nombre="CSAT Promedio Crítico",
        operador="<",
        valor_referencia=3.7,  # <P5 histórico semanal
        severidad=SeveridadAlerta.CRITICO,
        min_n=30,
        mensaje_plantilla="La satisfacción media ({valor:.2f}/5.0) cayó a nivel crítico (< {referencia:.1f}, N={n}).",
    ),
]
