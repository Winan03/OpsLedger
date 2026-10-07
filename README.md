# OpsLedger

OpsLedger es una torre de control operativa para convertir datos transaccionales reales en KPIs, alertas y reportes auditables.

## Fase actual

Fase 1A: esqueleto del proyecto y exploracion inicial del dataset Olist.

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

## Base de datos local

En desarrollo local se usa PostgreSQL 16 nativo en `localhost:5432`. La base y el usuario se llaman `opsledger`.

La aplicacion debe leer la conexion solo desde `DATABASE_URL` en `.env`. No se deben imprimir secretos ni pasar credenciales por parametros de comandos.

Para comprobar la conexion:

```powershell
.\.venv\Scripts\python.exe scripts\check_db_connection.py
```

`docker-compose.yml` queda solo como referencia de despliegue. No se usa en desarrollo local.

La API, el dashboard y el worker se agregaran en fases posteriores.
