from __future__ import annotations

import pandas as pd

from scripts.explorar_dataset import (
    check_relation,
    duplicate_primary_key_rows,
    order_coherence_checks,
)


def test_duplicate_primary_key_rows_counts_all_rows_with_repeated_key() -> None:
    df = pd.DataFrame(
        {
            "order_id": ["a", "a", "b"],
            "order_item_id": [1, 1, 1],
        }
    )

    assert duplicate_primary_key_rows(df, ["order_id", "order_item_id"]) == 2


def test_check_relation_reports_orphan_rows() -> None:
    tables = {
        "child.csv": pd.DataFrame({"order_id": ["o1", "o2", "o3"]}),
        "parent.csv": pd.DataFrame({"order_id": ["o1", "o3"]}),
    }

    result = check_relation(
        tables=tables,
        name="child.order_id -> parent.order_id",
        left_file="child.csv",
        left_column="order_id",
        right_file="parent.csv",
        right_column="order_id",
    )

    assert result["orphan_rows"] == 1
    assert result["sample_orphans"] == ["o2"]


def test_order_coherence_checks_detects_delivered_without_customer_delivery_date() -> None:
    tables = {
        "olist_orders_dataset.csv": pd.DataFrame(
            {
                "order_id": ["o1"],
                "order_status": ["delivered"],
                "order_purchase_timestamp": ["2018-01-01 10:00:00"],
                "order_approved_at": ["2018-01-01 11:00:00"],
                "order_delivered_carrier_date": ["2018-01-02 10:00:00"],
                "order_delivered_customer_date": [None],
                "order_estimated_delivery_date": ["2018-01-05 00:00:00"],
            }
        )
    }

    results = {
        result["name"]: result
        for result in order_coherence_checks(tables)
    }

    assert results["delivered_sin_fecha_entrega_cliente"]["rows"] == 1
    assert results["delivered_sin_fecha_entrega_cliente"]["sample_order_ids"] == ["o1"]
