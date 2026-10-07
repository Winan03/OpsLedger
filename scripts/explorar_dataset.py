from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "exploracion_olist.md"
TOP_N = 10

PRIMARY_KEYS: dict[str, list[str]] = {
    "olist_customers_dataset.csv": ["customer_id"],
    "olist_orders_dataset.csv": ["order_id"],
    "olist_order_items_dataset.csv": ["order_id", "order_item_id"],
    "olist_order_payments_dataset.csv": ["order_id", "payment_sequential"],
    "olist_order_reviews_dataset.csv": ["review_id"],
    "olist_products_dataset.csv": ["product_id"],
    "olist_sellers_dataset.csv": ["seller_id"],
    "product_category_name_translation.csv": ["product_category_name"],
}

EXPECTED_FILES: set[str] = {
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
}

RELATION_CHECKS: list[tuple[str, str, str, str, str]] = [
    (
        "orders.customer_id -> customers.customer_id",
        "olist_orders_dataset.csv",
        "customer_id",
        "olist_customers_dataset.csv",
        "customer_id",
    ),
    (
        "order_items.order_id -> orders.order_id",
        "olist_order_items_dataset.csv",
        "order_id",
        "olist_orders_dataset.csv",
        "order_id",
    ),
    (
        "order_payments.order_id -> orders.order_id",
        "olist_order_payments_dataset.csv",
        "order_id",
        "olist_orders_dataset.csv",
        "order_id",
    ),
    (
        "order_reviews.order_id -> orders.order_id",
        "olist_order_reviews_dataset.csv",
        "order_id",
        "olist_orders_dataset.csv",
        "order_id",
    ),
    (
        "order_items.product_id -> products.product_id",
        "olist_order_items_dataset.csv",
        "product_id",
        "olist_products_dataset.csv",
        "product_id",
    ),
    (
        "order_items.seller_id -> sellers.seller_id",
        "olist_order_items_dataset.csv",
        "seller_id",
        "olist_sellers_dataset.csv",
        "seller_id",
    ),
    (
        "products.product_category_name -> translation.product_category_name",
        "olist_products_dataset.csv",
        "product_category_name",
        "product_category_name_translation.csv",
        "product_category_name",
    ),
    (
        "customers.customer_zip_code_prefix -> geolocation.geolocation_zip_code_prefix",
        "olist_customers_dataset.csv",
        "customer_zip_code_prefix",
        "olist_geolocation_dataset.csv",
        "geolocation_zip_code_prefix",
    ),
    (
        "sellers.seller_zip_code_prefix -> geolocation.geolocation_zip_code_prefix",
        "olist_sellers_dataset.csv",
        "seller_zip_code_prefix",
        "olist_geolocation_dataset.csv",
        "geolocation_zip_code_prefix",
    ),
]

ORDER_DATE_COLUMNS: list[str] = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


@dataclass(frozen=True)
class TableProfile:
    file_name: str
    rows: int
    columns: int
    dtypes: dict[str, str]
    nulls: list[tuple[str, int, float]]
    duplicate_row_surplus: int
    duplicate_row_involved: int
    primary_key: list[str] | None
    duplicate_primary_key_surplus: int | None
    duplicate_primary_key_involved: int | None
    date_ranges: list[dict[str, Any]]
    top_values: dict[str, dict[str, int]]


def read_csv_files(raw_dir: Path) -> dict[str, pd.DataFrame]:
    if not raw_dir.exists():
        raise FileNotFoundError(f"No existe el directorio esperado: {raw_dir}")

    csv_paths = sorted(raw_dir.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"No se encontraron archivos CSV en: {raw_dir}")

    return {path.name: pd.read_csv(path, low_memory=False) for path in csv_paths}


def is_date_like_column(column_name: str) -> bool:
    normalized = column_name.lower()
    hints = ("date", "timestamp", "approved_at", "delivered", "estimated", "purchase", "limit")
    return any(hint in normalized for hint in hints)


def date_ranges(df: pd.DataFrame) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []

    for column in df.columns:
        if not is_date_like_column(column):
            continue

        parsed = pd.to_datetime(df[column], errors="coerce")
        non_null_original = int(df[column].notna().sum())
        valid_dates = int(parsed.notna().sum())
        invalid_dates = non_null_original - valid_dates

        ranges.append(
            {
                "column": column,
                "min": parsed.min(),
                "max": parsed.max(),
                "valid_dates": valid_dates,
                "invalid_dates": invalid_dates,
            }
        )

    return ranges


def top_status_and_category_values(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    selected: dict[str, dict[str, int]] = {}

    for column in df.columns:
        normalized = column.lower()
        if "status" not in normalized and "category" not in normalized:
            continue

        counts = df[column].fillna("<NULL>").astype(str).value_counts(dropna=False).head(TOP_N)
        selected[column] = {str(index): int(value) for index, value in counts.items()}

    return selected


def duplicate_metrics(df: pd.DataFrame, subset: list[str] | None = None) -> dict[str, int]:
    return {
        "surplus": int(df.duplicated(subset=subset, keep="first").sum()),
        "involved": int(df.duplicated(subset=subset, keep=False).sum()),
    }


def duplicate_primary_key_metrics(df: pd.DataFrame, key_columns: list[str] | None) -> dict[str, int] | None:
    if not key_columns:
        return None

    missing_columns = [column for column in key_columns if column not in df.columns]
    if missing_columns:
        return None

    return duplicate_metrics(df, key_columns)


def duplicate_primary_key_rows(df: pd.DataFrame, key_columns: list[str] | None) -> int:
    metrics = duplicate_primary_key_metrics(df, key_columns)
    if metrics is None:
        return 0
    return metrics["involved"]


def profile_table(file_name: str, df: pd.DataFrame) -> TableProfile:
    rows = int(len(df))
    nulls = [
        (column, int(count), round(float(count / rows * 100), 2) if rows else 0.0)
        for column, count in df.isna().sum().items()
    ]
    key_columns = PRIMARY_KEYS.get(file_name)
    row_duplicates = duplicate_metrics(df)
    primary_key_duplicates = duplicate_primary_key_metrics(df, key_columns)

    return TableProfile(
        file_name=file_name,
        rows=rows,
        columns=int(len(df.columns)),
        dtypes={column: str(dtype) for column, dtype in df.dtypes.items()},
        nulls=nulls,
        duplicate_row_surplus=row_duplicates["surplus"],
        duplicate_row_involved=row_duplicates["involved"],
        primary_key=key_columns,
        duplicate_primary_key_surplus=(
            None if primary_key_duplicates is None else primary_key_duplicates["surplus"]
        ),
        duplicate_primary_key_involved=(
            None if primary_key_duplicates is None else primary_key_duplicates["involved"]
        ),
        date_ranges=date_ranges(df),
        top_values=top_status_and_category_values(df),
    )


def sample_values(series: pd.Series, limit: int = 10) -> list[str]:
    return [str(value) for value in series.dropna().drop_duplicates().head(limit).tolist()]


def check_relation(
    tables: dict[str, pd.DataFrame],
    name: str,
    left_file: str,
    left_column: str,
    right_file: str,
    right_column: str,
) -> dict[str, Any]:
    left = tables[left_file]
    right = tables[right_file]

    left_non_null = left[left_column].dropna()
    right_values = set(right[right_column].dropna().unique())
    orphan_mask = ~left_non_null.isin(right_values)
    orphan_values = left_non_null[orphan_mask]

    return {
        "name": name,
        "left_file": left_file,
        "left_column": left_column,
        "right_file": right_file,
        "right_column": right_column,
        "left_rows": int(len(left)),
        "left_non_null": int(len(left_non_null)),
        "orphan_rows": int(orphan_mask.sum()),
        "orphan_distinct_values": int(orphan_values.nunique()),
        "sample_orphans": sample_values(orphan_values),
    }


def check_relations(tables: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for relation in RELATION_CHECKS:
        name, left_file, left_column, right_file, right_column = relation
        missing = [item for item in (left_file, right_file) if item not in tables]
        if missing:
            results.append({"name": name, "error": f"Faltan tablas: {', '.join(missing)}"})
            continue

        results.append(check_relation(tables, name, left_file, left_column, right_file, right_column))

    return results


def order_coherence_checks(tables: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    orders = tables.get("olist_orders_dataset.csv")
    if orders is None:
        return [{"name": "orders", "error": "No se encontro olist_orders_dataset.csv"}]

    parsed = orders.copy()
    for column in ORDER_DATE_COLUMNS:
        parsed[column] = pd.to_datetime(parsed[column], errors="coerce")

    checks: list[tuple[str, str, pd.Series]] = [
        (
            "entrega_cliente_antes_de_compra",
            "order_delivered_customer_date < order_purchase_timestamp",
            parsed["order_delivered_customer_date"] < parsed["order_purchase_timestamp"],
        ),
        (
            "delivered_sin_fecha_entrega_cliente",
            "order_status = delivered y order_delivered_customer_date es nula",
            parsed["order_status"].eq("delivered") & parsed["order_delivered_customer_date"].isna(),
        ),
        (
            "aprobacion_antes_de_compra",
            "order_approved_at < order_purchase_timestamp",
            parsed["order_approved_at"] < parsed["order_purchase_timestamp"],
        ),
        (
            "transportista_antes_de_aprobacion",
            "order_delivered_carrier_date < order_approved_at",
            parsed["order_delivered_carrier_date"] < parsed["order_approved_at"],
        ),
        (
            "entrega_cliente_antes_de_transportista",
            "order_delivered_customer_date < order_delivered_carrier_date",
            parsed["order_delivered_customer_date"] < parsed["order_delivered_carrier_date"],
        ),
        (
            "estimada_antes_de_compra",
            "order_estimated_delivery_date < order_purchase_timestamp",
            parsed["order_estimated_delivery_date"] < parsed["order_purchase_timestamp"],
        ),
        (
            "no_delivered_con_fecha_entrega_cliente",
            "order_status != delivered y order_delivered_customer_date no es nula",
            ~parsed["order_status"].eq("delivered") & parsed["order_delivered_customer_date"].notna(),
        ),
        (
            "delivered_sin_fecha_transportista",
            "order_status = delivered y order_delivered_carrier_date es nula",
            parsed["order_status"].eq("delivered") & parsed["order_delivered_carrier_date"].isna(),
        ),
        (
            "delivered_sin_fecha_aprobacion",
            "order_status = delivered y order_approved_at es nula",
            parsed["order_status"].eq("delivered") & parsed["order_approved_at"].isna(),
        ),
    ]

    results: list[dict[str, Any]] = []
    total_rows = int(len(parsed))

    for name, rule, mask in checks:
        mask = mask.fillna(False)
        affected = parsed.loc[mask, "order_id"]
        count = int(mask.sum())
        results.append(
            {
                "name": name,
                "rule": rule,
                "rows": count,
                "percent": round(float(count / total_rows * 100), 2) if total_rows else 0.0,
                "sample_order_ids": sample_values(affected),
            }
        )

    return results


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def format_timestamp(value: Any) -> str:
    if pd.isna(value):
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def render_profile(profile: TableProfile) -> str:
    null_rows = [[column, count, f"{percent:.2f}%"] for column, count, percent in profile.nulls]
    dtype_rows = [[column, dtype] for column, dtype in profile.dtypes.items()]
    date_rows = [
        [
            item["column"],
            format_timestamp(item["min"]),
            format_timestamp(item["max"]),
            item["valid_dates"],
            item["invalid_dates"],
        ]
        for item in profile.date_ranges
    ]

    key_text = ", ".join(profile.primary_key) if profile.primary_key else "No definido"
    duplicate_key_surplus_text = (
        "No aplica"
        if profile.duplicate_primary_key_surplus is None
        else str(profile.duplicate_primary_key_surplus)
    )
    duplicate_key_involved_text = (
        "No aplica"
        if profile.duplicate_primary_key_involved is None
        else str(profile.duplicate_primary_key_involved)
    )

    lines = [
        f"### {profile.file_name}",
        "",
        markdown_table(
            ["Metrica", "Valor"],
            [
                ["Filas", profile.rows],
                ["Columnas", profile.columns],
                ["Filas duplicadas completas sobrantes", profile.duplicate_row_surplus],
                ["Filas duplicadas completas involucradas", profile.duplicate_row_involved],
                ["Id principal evaluado", key_text],
                ["Filas sobrantes con id principal duplicado", duplicate_key_surplus_text],
                ["Filas involucradas con id principal duplicado", duplicate_key_involved_text],
            ],
        ),
        "",
        "#### Tipos de datos",
        "",
        markdown_table(["Columna", "Tipo pandas"], dtype_rows),
        "",
        "#### Nulos por columna",
        "",
        markdown_table(["Columna", "Nulos", "%"], null_rows),
    ]

    if date_rows:
        lines.extend(
            [
                "",
                "#### Rangos de fechas",
                "",
                markdown_table(
                    ["Columna", "Min", "Max", "Fechas validas", "Fechas invalidas"],
                    date_rows,
                ),
            ]
        )

    if profile.top_values:
        lines.extend(["", "#### Valores frecuentes en estado/categoria"])
        for column, values in profile.top_values.items():
            rows = [[value, count] for value, count in values.items()]
            lines.extend(["", f"**{column}**", "", markdown_table(["Valor", "Frecuencia"], rows)])

    return "\n".join(lines)


def render_findings(
    profiles: list[TableProfile],
    relation_results: list[dict[str, Any]],
    order_results: list[dict[str, Any]],
    loaded_files: set[str],
) -> str:
    missing_expected = sorted(EXPECTED_FILES - loaded_files)
    unexpected_files = sorted(loaded_files - EXPECTED_FILES)
    issues: list[str] = []
    confirmed_relations: list[str] = []

    if missing_expected:
        issues.append(f"Faltan archivos esperados: {', '.join(missing_expected)}.")
    if unexpected_files:
        issues.append(f"Hay archivos CSV no previstos: {', '.join(unexpected_files)}.")

    for profile in profiles:
        if profile.duplicate_row_surplus > 0:
            issues.append(
                f"`{profile.file_name}` tiene {profile.duplicate_row_surplus} filas duplicadas "
                f"completas sobrantes y {profile.duplicate_row_involved} filas involucradas."
            )
        if profile.duplicate_primary_key_surplus:
            key = ", ".join(profile.primary_key or [])
            issues.append(
                f"`{profile.file_name}` tiene {profile.duplicate_primary_key_surplus} filas "
                f"sobrantes y {profile.duplicate_primary_key_involved} filas involucradas "
                f"con id principal duplicado ({key})."
            )
        for item in profile.date_ranges:
            if item["invalid_dates"] > 0:
                issues.append(
                    f"`{profile.file_name}.{item['column']}` tiene {item['invalid_dates']} "
                    "fechas no parseables."
                )

    for result in relation_results:
        if result.get("error"):
            issues.append(f"`{result['name']}` no pudo evaluarse: {result['error']}.")
            continue
        if result["orphan_rows"] > 0:
            samples = ", ".join(result["sample_orphans"])
            issues.append(
                f"`{result['name']}` presenta {result['orphan_rows']} filas huerfanas "
                f"({result['orphan_distinct_values']} valores distintos). Ejemplos: {samples}."
            )
        else:
            confirmed_relations.append(f"`{result['name']}` sin huerfanos detectados.")

    for result in order_results:
        if result.get("error"):
            issues.append(f"`{result['name']}` no pudo evaluarse: {result['error']}.")
            continue
        if result["rows"] > 0:
            samples = ", ".join(result["sample_order_ids"])
            issues.append(
                f"`orders`: regla `{result['name']}` afecta {result['rows']} filas "
                f"({result['percent']:.2f}%). Ejemplos: {samples}."
            )

    if not issues:
        issues.append("No se detectaron problemas con las reglas exploratorias actuales.")

    date_rows: list[list[Any]] = []
    for profile in profiles:
        for item in profile.date_ranges:
            date_rows.append(
                [
                    profile.file_name,
                    item["column"],
                    format_timestamp(item["min"]),
                    format_timestamp(item["max"]),
                    item["valid_dates"],
                    item["invalid_dates"],
                ]
            )

    validation_rules = [
        "Cada tabla con id principal debe rechazar duplicados del id declarado.",
        "`orders.customer_id` debe existir en `customers.customer_id`.",
        "`order_items.order_id`, `order_payments.order_id` y `order_reviews.order_id` deben existir en `orders.order_id`.",
        "`order_items.product_id` debe existir en `products.product_id`.",
        "`order_items.seller_id` debe existir en `sellers.seller_id`.",
        "Las categorias no nulas de `products` deben existir en la tabla de traduccion.",
        "Una entrega al cliente no puede ser anterior a la compra.",
        "Un pedido `delivered` debe tener fecha de entrega al cliente.",
        "Las fechas deben seguir el orden compra <= aprobacion <= entrega a transportista <= entrega a cliente cuando existan.",
        "La fecha estimada de entrega no deberia ser anterior a la compra.",
    ]

    lines = [
        "# Exploracion inicial del dataset Olist",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Metricas de duplicados",
        "",
        "- **Filas sobrantes (`keep='first'`)**: Numero de filas redundantes que se eliminarian al desduplicar (se conserva la 1ra aparicion y se cuentan las sobrantes).",
        "- **Filas involucradas (`keep=False`)**: Numero total de filas que forman parte de algun grupo de duplicados (incluye la 1ra aparicion y todas sus repeticiones).",
        "",
        "## Clasificacion de valores nulos destacados",
        "",
        "### 1. Nulos esperables (opcionales por dinamica de negocio)",
        "- **`olist_order_reviews_dataset.csv`**: `review_comment_title` (87,656 nulos, 88.34%) y `review_comment_message` (58,247 nulos, 58.70%). Son **nulos esperables**: el cliente otorga una calificacion de 1 a 5 estrellas sin estar obligado a escribir un titulo o comentario en texto libre.",
        "",
        "### 2. Nulos por error de catalogo / datos faltantes",
        "- **`olist_products_dataset.csv`**: `product_category_name`, `product_name_lenght`, `product_description_lenght`, `product_photos_qty` (610 nulos, 1.85%). Son **errores / datos faltantes de catalogo**: fichas de producto incompletas registradas sin categoria ni metadata basica.",
        "- **`olist_products_dataset.csv`**: `product_weight_g`, `product_length_cm`, `product_height_cm`, `product_width_cm` (2 nulos, 0.01%). Son **errores / datos faltantes de catalogo**: atributos fisicos logisticos indispensables que omitieron su peso/dimensiones.",
        "",
        "## Archivos procesados",
        "",
        markdown_table(
            ["Archivo", "Filas", "Columnas"],
            [[profile.file_name, profile.rows, profile.columns] for profile in profiles],
        ),
        "",
        "## Problemas encontrados",
        "",
        "\n".join(f"- {issue}" for issue in issues),
        "",
        "## Relaciones confirmadas",
        "",
        "\n".join(f"- {relation}" for relation in confirmed_relations)
        if confirmed_relations
        else "- No se confirmaron relaciones sin huerfanos con las reglas actuales.",
        "",
        "## Columnas de fecha",
        "",
        markdown_table(
            ["Archivo", "Columna", "Min", "Max", "Fechas validas", "Fechas invalidas"],
            date_rows,
        )
        if date_rows
        else "No se detectaron columnas de fecha.",
        "",
        "## Reglas de validacion candidatas",
        "",
        "\n".join(f"- {rule}" for rule in validation_rules),
        "",
        "## Detalle por archivo",
        "",
        "\n\n".join(render_profile(profile) for profile in profiles),
        "",
        "## Integridad entre tablas",
        "",
        markdown_table(
            [
                "Relacion",
                "Filas evaluadas",
                "Filas no nulas",
                "Filas huerfanas",
                "Valores huerfanos distintos",
                "Ejemplos",
            ],
            [
                [
                    result.get("name", "-"),
                    result.get("left_rows", "-"),
                    result.get("left_non_null", "-"),
                    result.get("orphan_rows", "-"),
                    result.get("orphan_distinct_values", "-"),
                    ", ".join(result.get("sample_orphans", [])) or "-",
                ]
                for result in relation_results
            ],
        ),
        "",
        "## Coherencia temporal en orders",
        "",
        markdown_table(
            ["Regla", "Descripcion", "Filas", "%", "Ejemplos order_id"],
            [
                [
                    result.get("name", "-"),
                    result.get("rule", result.get("error", "-")),
                    result.get("rows", "-"),
                    result.get("percent", "-"),
                    ", ".join(result.get("sample_order_ids", [])) or "-",
                ]
                for result in order_results
            ],
        ),
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    tables = read_csv_files(RAW_DIR)
    profiles = [profile_table(file_name, tables[file_name]) for file_name in sorted(tables)]
    relation_results = check_relations(tables)
    order_results = order_coherence_checks(tables)
    report = render_findings(profiles, relation_results, order_results, set(tables))

    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Exploracion completada: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
