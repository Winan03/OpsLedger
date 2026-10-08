# OpsLedger — Especificación y Fichas Técnicas de KPIs (Fase 2A)

Este documento define la especificación matemática, operativa, dimensional y de calidad para los 8 Indicadores Clave de Rendimiento (KPIs) del sistema OpsLedger.

---

## 1. Convenciones Globales y Criterios Transversales

### 1.1 Fechas de Referencia para Agregación Temporal
Cada KPI responde a una etapa específica del ciclo de vida del pedido. Para evitar sesgos de medición y desfases temporales, cada indicador se agrupa por su fecha natural de ocurrencia:

| Tipo de Métrica | KPIs Asociados | Fecha / Marca de Tiempo de Referencia | Justificación |
|---|---|---|---|
| **Nivel de Servicio / Entrega** | KPI 1 (Ciclo), KPI 2 (OTD), KPI 3 (Desviación) | `fecha_entrega_cliente` (Semana / Mes de entrega) | Mide el servicio percibido en el momento en que el cliente efectivamente recibió el producto. |
| **Logística de Despacho (Fulfillment)** | KPI 4 (Tiempo de Despacho del Vendedor) | `fecha_entrega_transportista` (Semana / Mes de despacho) | Mide la eficiencia del vendedor al momento de traspasar la custodia al operador logístico. |
| **Comercial, Financiero y Abandono** | KPI 5 (Costo Flete), KPI 6 (Ventas e Ingresos), KPI 7 (Cancelación) | `fecha_compra` (Semana / Mes de compra) | Mide la generación de demanda, facturación y fricción transaccional al momento de la orden. |
| **Satisfacción del Cliente (CSAT)** | KPI 8 (Satisfacción vs Retraso) | `fecha_creacion` de la reseña | Refleja la percepción y evaluación en la fecha en que el cliente emitió su opinión. |

### 1.2 Dimensión Geográfica (Región)
- **Estado del Cliente (`cliente_estado`):** Utilizado para KPIs de entrega al cliente (1, 2, 3), costo de flete e ingresos (5, 6) y cancelaciones (7).
- **Estado del Vendedor (`vendedor_estado`):** Utilizado para el KPI 4 (Despacho del vendedor) para auditar la agilidad operativa por centro de despacho o estado de origen.

### 1.3 Filtrado Seguro por Categoría o Vendedor (Regla Anti-Multiplicación)
Para los KPIs evaluados a nivel de pedido o reseña (KPIs 1 a 4, 7 y 8), cuando se filtra por categoría de producto o por vendedor, **está estrictamente prohibido hacer `JOIN` con `items_pedido`**, ya que un pedido con $N$ ítems duplicaría el pedido $N$ veces, sesgando medias, porcentajes y conteos.
En su lugar, se utiliza **`EXISTS` (Semi-Join)**:
```sql
AND EXISTS (
    SELECT 1 
    FROM operativo.items_pedido i
    JOIN operativo.productos pr ON i.producto_id = pr.producto_id
    WHERE i.pedido_id = p.pedido_id
      AND pr.categoria_nombre = :categoria
)
```

### 1.4 Umbrales de Alerta y Calibración Empírica (`min_n`)
Toda alerta por desviación de umbral requiere un tamaño de muestra mínimo ($N \ge \text{min\_n}$) en la cohorte o periodo evaluado para evitar falsos positivos causados por volatilidad muestral. 

Los umbrales se calibran a partir de la **distribución histórica de percentiles semanales** (85 semanas entre 2017 y 2018 con $N \ge 30$) calculada mediante la consulta:
```sql
WITH metricas_semanales AS (
    SELECT 
        DATE_TRUNC('week', fecha_entrega_cliente) AS semana,
        COUNT(*) AS n_pedidos,
        AVG(tiempo_ciclo_dias) AS ciclo_dias,
        (COUNT(*) FILTER (WHERE es_a_tiempo)::numeric / COUNT(*) * 100) AS otd_pct,
        AVG(desviacion_plazo_dias) FILTER (WHERE NOT es_a_tiempo) AS retraso_tardios_dias
    FROM analytics.fct_pedidos
    WHERE es_valido_ciclo_otd = TRUE
      AND fecha_entrega_cliente BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY DATE_TRUNC('week', fecha_entrega_cliente)
    HAVING COUNT(*) >= 30
)
SELECT 
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY retraso_tardios_dias)::numeric, 2) AS p50_retraso,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY retraso_tardios_dias)::numeric, 2) AS p75_retraso,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY retraso_tardios_dias)::numeric, 2) AS p90_retraso;
```
*Nota:* Los umbrales configurados son ilustrativos y configurables desde `src/modules/kpis/config.py`.

### 1.5 Reconciliación Financiera: Ventas Brutas vs. Ingresos Realizados
- **Ventas Brutas (`es_venta_bruta` en `fct_pedidos`):** Suma de `precio + valor_flete` de todos los pedidos activos y confirmados. Excluye estrictamente órdenes no concretadas (`estado_pedido IN ('canceled', 'unavailable')`).
- **Ingresos Realizados (`es_ingreso_realizado` en `fct_pedidos`):** Suma de `precio + valor_flete` exclusivamente de pedidos con entrega confirmada (`estado_pedido = 'delivered'`).
- **Los 6 Pedidos `unavailable` con ítems (R$ 2,140.49):**
  Al definir formalmente Ventas Brutas excluyendo `canceled` y `unavailable`, se descartan exactamente 6 pedidos que tenían ítems asignados pero su estado final fue `unavailable`:
  - `1a47da1d66c70489c8e35fe2b5433ab7` (R$ 270.75)
  - `2fd1c83dd4714cf3cf796fffb6c8de62` (R$ 192.19)
  - `3c3ca08854ca922fe8e9cedfd6841c8a` (R$ 45.96)
  - `4dd47e84e6b8ff4a63d0b8425e6d788e` (R$ 313.58)
  - `54bb06e1ca86bd99ee2a8d6288bf4ede` (R$ 90.23)
  - `dc18a044b56ed174037ca164cdf2e921` (R$ 1,227.78)
  - Total: **R$ 2,007.69** en productos + **R$ 132.80** en flete = **R$ 2,140.49**. Al excluirlos, las ventas brutas pasan exactamente de R$ 15,737,667.52 (98,205 pedidos) a **R$ 15,735,527.03** (98,199 pedidos facturados activos).

- **Ecuación de Partición y Reconciliación Exacta con `pagos_pedido`:**
  - Total `pagos_pedido` (`monto_pago`): **R$ 16,008,872.12**
  - Total `items_pedido` (`precio + flete`): **R$ 15,843,553.24**
  - Diferencia bruta global: **+R$ 165,318.88** (los pagos superan a los ítems).

  El universo íntegro de 99,441 pedidos se particiona en 3 conjuntos disjuntos que cuadran la diferencia al centavo exacto:
  $$\text{Diferencia Global} = \text{Solo Pagos} - \text{Solo Ítems} + \text{Saldo Ambos}$$
  $$\text{R\$\ 165,318.88} = \text{R\$\ 162,591.95} - \text{R\$\ 143.46} + \text{R\$\ 2,870.39}$$

  1. **Pedidos con SOLO PAGOS y sin ítems (775 pedidos / +R$ 162,591.95):**
     - 603 pedidos `unavailable`: R$ 124,339.02
     - 164 pedidos `canceled`: R$ 37,337.87
     - 5 pedidos `created`: R$ 688.10 (IDs: `35de40...`, `7a4df5...`, `90ab3e...`, `b53599...`, `dba506...`)
     - 2 pedidos `invoiced`: R$ 149.23 (IDs: `2ce968...`, `e04f1da...`)
     - 1 pedido `shipped`: R$ 77.73 (ID: `a68ce1...`)
  2. **Pedidos con SOLO ÍTEMS y sin pagos (1 pedido / -R$ 143.46):**
     - Pedido `bfbd0f9bdef84302105ad712db648a6c` (`delivered`, 3 ítems: R$ 134.97 productos + R$ 8.49 flete = R$ 143.46).
  3. **Pedidos con ÍTEMS y PAGOS (98,665 pedidos / Saldo neto: +R$ 2,870.39):**
     - 98,089 pedidos (**99.42%**): Coincidencia idéntica ($\text{diff} = 0.00$).
     - 273 pedidos: Diferencias de **1 centavo** por redondeo ($0 < |\text{diff}| \le 0.01$), sumando **-R$ 0.67**.
     - 264 pedidos: Pagos > Items ($\text{diff} > 0.01$), sumando **+R$ 3,070.14** (el **94.3%** son compras en cuotas $>1$). *Hipótesis:* Intereses y costos de financiamiento de pasarelas de pago.
     - 39 pedidos: Items > Pagos ($\text{diff} < -0.01$), sumando **-R$ 199.08**. *Hipótesis:* Cupones o descuentos comerciales en el carrito.
     - *Saldo neto en ambos:* $+3,070.14 - 199.08 - 0.67 = \mathbf{+R\$\ 2,870.39}$.
  $$\text{Total pedidos auditados} = 775 + 1 + 98,665 = \mathbf{99,441 \text{ pedidos (100\%)}}$$

---

## 2. Fichas Técnicas de los 8 KPIs

---

### FICHA KPI-01: Tiempo de Ciclo del Pedido (Lead Time de Entrega)

- **Pregunta de Negocio:** ¿Cuántos días transcurren en promedio desde que el cliente realiza la compra hasta que recibe físicamente su paquete?
- **Fórmula Matemática:**
  $$\text{Tiempo de Ciclo (días)} = \frac{1}{N} \sum_{i=1}^N \frac{\text{fecha\_entrega\_cliente}_i - \text{fecha\_compra}_i}{86400 \text{ s}}$$
- **Fecha de Referencia:** `fecha_entrega_cliente` (Semana / Mes de entrega al cliente).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.pedidos (fecha_compra, fecha_entrega_cliente, estado_pedido, banderas_calidad)`.
- **Regla de Exclusión por Calidad:**
  - `estado_pedido = 'delivered'` y `fecha_entrega_cliente IS NOT NULL`.
  - Excluye bandera `sin_fecha_entrega_cliente` (8 pedidos).
  - *Decisión sobre las 23 filas de `entrega_cliente_antes_de_transportista`:* Se **conservan** en este KPI porque la `fecha_compra` y la `fecha_entrega_cliente` son válidas y coherentes; el error de registro afectó únicamente al sello intermedio del transportista. (Diferencia global: $0.0014$ días).
- **Consulta SQL:**
  ```sql
  SELECT 
      COUNT(*) AS total_pedidos_evaluados,
      ROUND(AVG(EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_compra)) / 86400.0)::numeric, 2) AS tiempo_ciclo_medio_dias,
      ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_compra)) / 86400.0)::numeric, 2) AS tiempo_ciclo_mediana_dias
  FROM operativo.pedidos p
  WHERE p.estado_pedido = 'delivered'
    AND p.fecha_entrega_cliente IS NOT NULL
    AND NOT (p.banderas_calidad ? 'sin_fecha_entrega_cliente');
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* Media semanal $> 14.5$ días ($\text{min\_n} = 30$, ~P80 histórico semanal).
  - *Crítico:* Media semanal $> 16.0$ días ($\text{min\_n} = 30$, ~P92 histórico semanal).
- **Valor Global Real Validado:** **12.56 días** (Mediana: **10.22 días**; 96,470 pedidos evaluados).

---

### FICHA KPI-02: Cumplimiento de Entrega (On-Time Delivery - OTD)

- **Pregunta de Negocio:** ¿Qué porcentaje de los pedidos entregados llegaron en o antes de la fecha estimada comprometida con el cliente?
- **Fórmula Matemática:**
  $$\text{OTD (\%)} = \frac{\sum [\text{fecha\_entrega\_cliente} \le \text{fecha\_estimada\_entrega}]}{N_{\text{entregados}}} \times 100$$
- **Fecha de Referencia:** `fecha_entrega_cliente` (Semana / Mes de entrega al cliente).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.pedidos (fecha_entrega_cliente, fecha_estimada_entrega, estado_pedido, banderas_calidad)`.
- **Regla de Exclusión por Calidad:**
  - Excluye pedidos no `delivered` y bandera `sin_fecha_entrega_cliente`.
  - Se conservan las 23 filas de orden invertido (diferencia: $0.0019\%$).
- **Consulta SQL (con filtro opcional de categoría vía `EXISTS`):**
  ```sql
  SELECT 
      COUNT(*) AS total_pedidos_entregados,
      COUNT(*) FILTER (WHERE p.fecha_entrega_cliente <= p.fecha_estimada_entrega) AS entregados_a_tiempo,
      ROUND((COUNT(*) FILTER (WHERE p.fecha_entrega_cliente <= p.fecha_estimada_entrega)::numeric / NULLIF(COUNT(*), 0)) * 100, 2) AS otd_pct
  FROM operativo.pedidos p
  WHERE p.estado_pedido = 'delivered'
    AND p.fecha_entrega_cliente IS NOT NULL
    AND NOT (p.banderas_calidad ? 'sin_fecha_entrega_cliente');
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* OTD semanal $< 88.0\%$ ($\text{min\_n} = 50$, cercano a P10 histórico).
  - *Crítico:* OTD semanal $< 82.0\%$ ($\text{min\_n} = 50$, cercano a P5 histórico).
- **Valor Global Real Validado:** **91.89%** (88,644 pedidos a tiempo de 96,470 entregados).

---

### FICHA KPI-03: Desviación de Plazo de Entrega (Delivery Delay / Advance)

- **Pregunta de Negocio:** ¿Con cuánto adelanto o retraso relativo (en días) se entregan los pedidos respecto a la promesa logística?
- **Fórmula Matemática:**
  $$\text{Desviación (días)} = \frac{1}{N} \sum_{i=1}^N \frac{\text{fecha\_entrega\_cliente}_i - \text{fecha\_estimada\_entrega}_i}{86400 \text{ s}}$$
- **Fecha de Referencia:** `fecha_entrega_cliente` (Semana / Mes de entrega al cliente).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.pedidos (fecha_entrega_cliente, fecha_estimada_entrega, estado_pedido, banderas_calidad)`.
- **Regla de Exclusión por Calidad:** Excluye pedidos no `delivered` y bandera `sin_fecha_entrega_cliente`.
- **Consulta SQL:**
  ```sql
  SELECT 
      ROUND(AVG(EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_estimada_entrega)) / 86400.0)::numeric, 2) AS desviacion_media_global_dias,
      ROUND(AVG(EXTRACT(EPOCH FROM (p.fecha_entrega_cliente - p.fecha_estimada_entrega)) / 86400.0) 
            FILTER (WHERE p.fecha_entrega_cliente > p.fecha_estimada_entrega)::numeric, 2) AS retraso_medio_pedidos_tardios_dias,
      COUNT(*) FILTER (WHERE p.fecha_entrega_cliente > p.fecha_estimada_entrega) AS total_pedidos_tardios
  FROM operativo.pedidos p
  WHERE p.estado_pedido = 'delivered'
    AND p.fecha_entrega_cliente IS NOT NULL
    AND NOT (p.banderas_calidad ? 'sin_fecha_entrega_cliente');
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* Retraso medio en pedidos tardíos $> 12.0$ días ($\text{min\_n} = 20$, correspondiente a P75 histórico donde la demora es 25% superior a la habitual).
  - *Crítico:* Retraso medio en pedidos tardíos $> 16.0$ días ($\text{min\_n} = 20$, $>$ P90 histórico en semanas de colapso logístico).
- **Valor Global Real Validado:**
  - Desviación global promedio: **-11.18 días** (compromiso conservador).
  - Retraso promedio en pedidos tardíos: **+9.55 días** (7,826 pedidos; mediana semanal típica: 8.77 días).

---

### FICHA KPI-04: Tiempo de Despacho del Vendedor (Fulfillment / Dispatch Time)

- **Pregunta de Negocio:** ¿Cuánto tarda un vendedor en preparar y entregar el paquete al transportista tras aprobarse el pago?
- **Fórmula Matemática:**
  $$\text{Tiempo de Despacho (días)} = \frac{1}{N} \sum_{i=1}^N \frac{\text{fecha\_entrega\_transportista}_i - \text{fecha\_aprobacion}_i}{86400 \text{ s}}$$
- **Fecha de Referencia:** `fecha_entrega_transportista` (Semana / Mes de entrega al transportista).
- **Región de Referencia:** **Estado del vendedor** (`operativo.vendedores.estado_region`).
- **Columnas Utilizadas:** `operativo.pedidos (fecha_aprobacion, fecha_entrega_transportista, banderas_calidad)`.
- **Regla de Exclusión por Calidad:**
  - Excluye `fecha_entrega_transportista IS NULL` o `fecha_aprobacion IS NULL`.
  - Excluye bandera `sin_fecha_aprobacion` (14 pedidos).
  - Excluye bandera `despacho_antes_de_aprobacion` (1,359 pedidos).
  - **Excluye bandera `entrega_cliente_antes_de_transportista` (23 pedidos):** Al tener un sello de transportista posterior a la entrega al cliente, el tiempo de despacho registrado es ficticiamente alto e incoherente.
- **Consulta SQL:**
  ```sql
  SELECT 
      COUNT(*) AS pedidos_evaluados,
      ROUND(AVG(EXTRACT(EPOCH FROM (p.fecha_entrega_transportista - p.fecha_aprobacion)) / 86400.0)::numeric, 2) AS despacho_medio_dias,
      ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (p.fecha_entrega_transportista - p.fecha_aprobacion)) / 86400.0)::numeric, 2) AS despacho_mediana_dias
  FROM operativo.pedidos p
  WHERE p.fecha_entrega_transportista IS NOT NULL
    AND p.fecha_aprobacion IS NOT NULL
    AND NOT (p.banderas_calidad ? 'sin_fecha_aprobacion')
    AND NOT (p.banderas_calidad ? 'despacho_antes_de_aprobacion')
    AND NOT (p.banderas_calidad ? 'entrega_cliente_antes_de_transportista');
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* Media semanal $> 3.3$ días ($\text{min\_n} = 25$, P90 histórico semanal).
  - *Crítico:* Media semanal $> 4.0$ días ($\text{min\_n} = 25$, > P95 histórico semanal).
- **Valor Global Real Validado:** **2.86 días** (Mediana: **1.85 días**; 96,262 pedidos evaluados tras excluir las 23 filas).

---

### FICHA KPI-05: Costo Logístico Relativo (Freight to Product Ratio)

- **Pregunta de Negocio:** ¿Qué porcentaje del valor bruto del producto representa el flete pagado por el comprador?
- **Fórmula Matemática:**
  $$\text{Costo Logístico Relativo (\%)} = \frac{\sum \text{valor\_flete}}{\sum \text{precio}} \times 100$$
- **Fecha de Referencia:** `fecha_compra` (Semana / Mes de compra).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.items_pedido (precio, valor_flete), operativo.pedidos (estado_pedido, fecha_compra)`.
- **Regla de Exclusión por Calidad:** Comparte la misma definición de **ventas brutas** que el KPI 6 (`p.es_venta_bruta = TRUE`), excluyendo órdenes canceladas e indisponibles (`canceled`, `unavailable`).
- **Consulta SQL:**
  ```sql
  SELECT 
      ROUND(SUM(i.precio)::numeric, 2) AS valor_total_productos,
      ROUND(SUM(i.valor_flete)::numeric, 2) AS valor_total_flete,
      ROUND((SUM(i.valor_flete) / NULLIF(SUM(i.precio), 0) * 100)::numeric, 2) AS costo_logistico_relativo_pct
  FROM analytics.fct_items_pedido i
  JOIN analytics.fct_pedidos p ON i.pedido_id = p.pedido_id
  WHERE p.es_venta_bruta = TRUE;
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* Flete relativo $> 18.0\%$ ($\text{min\_n} = 30$, P90 histórico semanal).
  - *Crítico:* Flete relativo $> 20.0\%$ ($\text{min\_n} = 30$, > P95 histórico semanal).
- **Valor Global Real Validado:** **16.61%** (Flete: R$ 2,241,126.29 / Productos: R$ 13,494,400.74; 98,199 pedidos con ítems).

---

### FICHA KPI-06: Ventas Brutas, Ingresos Realizados y Ticket Promedio (AOV)

- **Pregunta de Negocio:** ¿Cuál es el volumen monetario transaccionado, la facturación efectivamente realizada y el gasto promedio por pedido?
- **Fórmula Matemática:**
  - $\text{Ventas Brutas} = \sum (\text{precio} + \text{valor\_flete}) \quad [\text{estado\_pedido} \notin (\text{'canceled'}, \text{'unavailable'})]$
  - $\text{Ingresos Realizados} = \sum (\text{precio} + \text{valor\_flete}) \quad [\text{estado\_pedido} = \text{'delivered'}]$
  - $\text{Ticket Promedio (AOV)} = \frac{\text{Ventas Brutas}}{N_{\text{pedidos facturados}}}$
- **Fecha de Referencia:** `fecha_compra` (Semana / Mes de compra).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.items_pedido (precio, valor_flete), operativo.pedidos (pedido_id, estado_pedido, fecha_compra)`.
- **Consulta SQL:**
  ```sql
  WITH totales_por_pedido AS (
      SELECT 
          p.pedido_id,
          p.estado_pedido,
          SUM(i.precio) AS subtotal_productos,
          SUM(i.precio + i.valor_flete) AS total_pedido
      FROM operativo.pedidos p
      JOIN operativo.items_pedido i ON p.pedido_id = i.pedido_id
      WHERE p.estado_pedido NOT IN ('canceled', 'unavailable')
      GROUP BY p.pedido_id, p.estado_pedido
  )
  SELECT 
      COUNT(*) AS total_pedidos_ventas_brutas,
      ROUND(SUM(total_pedido)::numeric, 2) AS ventas_brutas_totales,
      ROUND(SUM(total_pedido) FILTER (WHERE estado_pedido = 'delivered')::numeric, 2) AS ingresos_realizados_totales,
      ROUND(AVG(total_pedido)::numeric, 2) AS ticket_promedio_total,
      ROUND(AVG(subtotal_productos)::numeric, 2) AS ticket_promedio_sin_flete
  FROM totales_por_pedido;
  ```
- **Umbral de Alerta Sugerido:**
  - *Advertencia:* Caída de ventas brutas semanales $> 15.0\%$ vs semana previa ($\text{min\_n} = 50$).
  - *Crítico:* Caída de ventas brutas semanales $> 25.0\%$ ($\text{min\_n} = 50$).
- **Valor Global Real Validado:**
  - Ventas Brutas Totales: **R$ 15,735,527.03** (98,199 pedidos facturados activos).
  - Ingresos Realizados (`delivered`): **R$ 15,419,773.75** (96,478 pedidos con entrega confirmada).
  - Ticket Promedio Total: **R$ 160.24** (Ticket Productos: **R$ 137.42**).

---

### FICHA KPI-07: Tasa de Cancelación y Pérdida Operativa

- **Pregunta de Negocio:** ¿Qué porcentaje de las órdenes no llegan a concretarse debido a cancelación del comprador o falta de inventario?
- **Fórmula Matemática:**
  - $\text{Tasa de Cancelación Directa (\%)} = \frac{\text{COUNT}(\text{estado\_pedido} = \text{'canceled'})}{N_{\text{total pedidos}}} \times 100$
  - $\text{Tasa de Falla Operativa Total (\%)} = \frac{\text{COUNT}(\text{estado\_pedido} \in (\text{'canceled'}, \text{'unavailable'}))}{N_{\text{total pedidos}}} \times 100$
- **Fecha de Referencia:** `fecha_compra` (Semana / Mes de compra).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.pedidos (estado_pedido, fecha_compra)`.
- **Regla de Exclusión por Calidad:** Ninguna (evalúa el universo íntegro de 99,441 pedidos).
- **Consulta SQL:**
  ```sql
  SELECT 
      COUNT(*) AS total_pedidos,
      COUNT(*) FILTER (WHERE estado_pedido = 'canceled') AS pedidos_cancelados,
      COUNT(*) FILTER (WHERE estado_pedido = 'unavailable') AS pedidos_no_disponibles,
      ROUND((COUNT(*) FILTER (WHERE estado_pedido = 'canceled')::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS tasa_cancelacion_pct,
      ROUND((COUNT(*) FILTER (WHERE estado_pedido IN ('canceled', 'unavailable'))::numeric / NULLIF(COUNT(*), 0) * 100), 2) AS tasa_falla_operativa_pct
  FROM operativo.pedidos;
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Mensual):**
  - *Advertencia:* Tasa de cancelación mensual $> 1.0\%$ ($\text{min\_n} = 50$, ~P85 histórico mensual).
  - *Crítico:* Tasa de cancelación mensual $> 1.5\%$ ($\text{min\_n} = 50$, > P95 histórico mensual).
- **Valor Global Real Validado:**
  - Tasa de Cancelación Directa: **0.63%** (625 pedidos).
  - Tasa de Falla Operativa Total: **1.24%** (1,234 pedidos).

---

### FICHA KPI-08: Satisfacción del Cliente (CSAT) vs. Retraso en Entrega

- **Pregunta de Negocio:** ¿Cuál es el puntaje promedio por reseña y cómo se asocia la demora en la entrega con la insatisfacción del cliente?
- **Fórmula Matemática:**
  $$\text{CSAT Promedio} = \frac{1}{N_{\text{reseñas}}} \sum_{j=1}^{N_{\text{reseñas}}} \text{puntaje}_j$$
  Segmentado por condición del pedido: Entregado a tiempo vs. Entregado con retraso vs. Cancelado.
- **Fecha de Referencia:** `fecha_creacion` de la reseña (`operativo.resenas_pedido.fecha_creacion`).
- **Región de Referencia:** Estado del cliente (`operativo.clientes.estado_region`).
- **Columnas Utilizadas:** `operativo.resenas_pedido (puntaje, fecha_creacion), operativo.pedidos (fecha_entrega_cliente, fecha_estimada_entrega, estado_pedido)`.
- **Aclaración Metodológica:** El promedio se calcula **por reseña emitida** (no por pedido, dado que un cliente puede emitir una reseña sobre su experiencia global).
- **Consulta SQL:**
  ```sql
  WITH resenas_con_segmento AS (
      SELECT 
          r.puntaje,
          CASE 
              WHEN p.estado_pedido = 'canceled' THEN 'Cancelado'
              WHEN p.fecha_entrega_cliente IS NULL THEN 'Sin entrega confirmada'
              WHEN p.fecha_entrega_cliente <= p.fecha_estimada_entrega THEN 'A tiempo'
              ELSE 'Con retraso'
          END AS segmento_entrega
      FROM operativo.resenas_pedido r
      JOIN operativo.pedidos p ON r.pedido_id = p.pedido_id
  )
  SELECT 
      ROUND(AVG(puntaje)::numeric, 2) AS csat_promedio_global,
      ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'A tiempo')::numeric, 2) AS csat_a_tiempo,
      ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'Con retraso')::numeric, 2) AS csat_con_retraso,
      ROUND(AVG(puntaje) FILTER (WHERE segmento_entrega = 'Cancelado')::numeric, 2) AS csat_cancelados,
      COUNT(*) FILTER (WHERE segmento_entrega = 'A tiempo') AS n_resenas_a_tiempo,
      COUNT(*) FILTER (WHERE segmento_entrega = 'Con retraso') AS n_resenas_con_retraso
  FROM resenas_con_segmento;
  ```
- **Umbral de Alerta Sugerido (Calibrado con Histórico Semanal):**
  - *Advertencia:* CSAT global semanal $< 3.9 / 5.0$ ($\text{min\_n} = 30$, P10 histórico semanal).
  - *Crítico:* CSAT global semanal $< 3.7 / 5.0$ ($\text{min\_n} = 30$, < P5 histórico semanal).
- **Valor Global Real Validado:**
  - CSAT Global: **4.09 / 5.0** (99,224 reseñas).
  - Reseñas de entregas a tiempo (88,653 reseñas): **4.29 / 5.0**.
  - Reseñas de entregas con retraso (7,700 reseñas): **2.57 / 5.0** *(Caída crítica de 1.72 estrellas **asociada** al retraso logístico)*.
  - Reseñas de cancelados (618 reseñas): **1.81 / 5.0**.
