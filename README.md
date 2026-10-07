# OpsLedger

OpsLedger es una torre de control operativa para convertir datos transaccionales reales en KPIs, alertas y reportes auditables.

## Fase actual

Fase 1C: ETL de ingesta — carga de CSV Olist a PostgreSQL (staging → operativo).

## Stack base

- Python 3.12
- PostgreSQL 16
- SQLAlchemy + Alembic
- Pandas / Polars
- FastAPI
- Streamlit + Plotly
- WeasyPrint
- Docker Compose
- Pytest

## Primeros comandos

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\explorar_dataset.py
```

## Migraciones

```powershell
# Aplicar todas las migraciones (crea esquemas + tablas)
.\.venv\Scripts\alembic.exe upgrade head

# Ver revisión actual
.\.venv\Scripts\alembic.exe current
```

## Ingesta ETL (Fase 1C)

Carga los archivos CSV de Olist en orden de claves foráneas:
categorías → clientes → vendedores → productos → pedidos → ítems → pagos → reseñas.

```powershell
# Primera carga
.\.venv\Scripts\python.exe -m src.modules.ingesta --dir data/raw

# Segunda ejecución: informa "ya procesado" por cada archivo (idempotente)
.\.venv\Scripts\python.exe -m src.modules.ingesta --dir data/raw
```

Los informes de calidad por archivo se guardan en `reports/calidad/` (no versionados).

## Tests

```powershell
.\.venv\Scripts\pytest.exe tests/ -v
```

Los tests de ingesta y migraciones usan `TEST_DATABASE_URL` (base `opsledger_test`).
Nunca tocan la base de desarrollo.

## Base de datos local

En desarrollo local se usa PostgreSQL 16 nativo en `localhost:5432`. La base y el usuario se llaman `opsledger`.

La aplicacion debe leer la conexion solo desde `DATABASE_URL` en `.env`. No se deben imprimir secretos ni pasar credenciales por parametros de comandos.

Para comprobar la conexion:

```powershell
.\.venv\Scripts\python.exe scripts\check_db_connection.py
```

`docker-compose.yml` queda solo como referencia de despliegue. No se usa en desarrollo local.

## Estructura del proyecto

La arquitectura modular en capas (`src/modules`, `src/worker`, `src/dashboard`) representa el objetivo final del proyecto. Los módulos y componentes se crean de forma incremental fase por fase a medida que se desarrolla el código correspondiente (en la Fase 1B/1C se habilita `src/modules/ingesta/`).

