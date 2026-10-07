"""Punto de entrada CLI para la ingesta.

Uso:
    python -m src.modules.ingesta --dir data/raw
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path al ejecutar con -m
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Cargar variables de entorno desde .env antes de importar config
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    import os
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _cleaned = _line.strip()
        if _cleaned and not _cleaned.startswith("#") and "=" in _cleaned:
            _k, _v = _cleaned.split("=", 1)
            _k = _k.strip()
            if _k not in os.environ:
                os.environ[_k] = _v.strip().strip('"').strip("'")

from src.modules.ingesta.service import ejecutar_ingesta  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta ETL: carga CSV de Olist en la base operativa.",
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Directorio que contiene los archivos CSV de Olist (ej. data/raw).",
    )
    args = parser.parse_args()

    data_dir = args.dir.resolve()
    if not data_dir.is_dir():
        print(f"Error: el directorio '{data_dir}' no existe.", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== OpsLedger — Ingesta ETL ===")
    print(f"Directorio de datos: {data_dir}\n")

    resultados = ejecutar_ingesta(data_dir)

    print("\n=== Resumen final ===")
    for r in resultados:
        if r.get("ya_procesado"):
            print(f"  [OMITIDO] {r['nombre']}: ya procesado")
        else:
            print(
                f"  [OK] {r['nombre']}: "
                f"leidos={r['leidos']}  aceptados={r['aceptados']}  "
                f"rechazados={r['rechazados']}  con_bandera={r['con_bandera']}"
            )
    print()


if __name__ == "__main__":
    main()
