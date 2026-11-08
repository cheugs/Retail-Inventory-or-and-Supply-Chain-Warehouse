"""Unit tests of the file schema checks done before loading (no database needed)."""
import pytest

from retail_pipeline.ingest import ENTITIES, SchemaError, check_header, read_rows


def test_known_header_is_accepted():
    columns, unknown = check_header("sales", ENTITIES["sales"]["columns"])
    assert columns == ENTITIES["sales"]["columns"]
    assert unknown == []


def test_missing_mandatory_column_is_refused():
    header = [c for c in ENTITIES["sales"]["columns"] if c != "quantity"]
    with pytest.raises(SchemaError, match="quantity"):
        check_header("sales", header)


def test_unknown_new_column_is_reported_not_loaded():
    header = ENTITIES["sales"]["columns"] + ["loyalty_card"]
    columns, unknown = check_header("sales", header)
    assert unknown == ["loyalty_card"]
    assert "loyalty_card" not in columns


def test_old_file_without_optional_column(tmp_path):
    # files written before the "channel" column existed must still load
    path = tmp_path / "sales.csv"
    path.write_text(
        "sale_line_id,receipt_id,store_id,product_id,sold_at,quantity,unit_price,discount_amount,currency\n"
        "SL1,R1,S01,P0001,2026-01-01 10:00:00,2,3.50,,EUR\n",
        encoding="utf-8",
    )
    columns, unknown, rows = read_rows(path, "sales")
    values, line = rows[0]
    record = dict(zip(columns, values))
    assert line == 1
    assert record["channel"] is None          # absent column -> NULL
    assert record["discount_amount"] is None  # empty value -> NULL
    assert record["quantity"] == "2"          # values stay text in the raw layer


def test_columns_can_be_in_any_order(tmp_path):
    path = tmp_path / "fx_rates.csv"
    path.write_text("currency,rate_to_eur,rate_date\nCHF,1.06,2026-01-01\n", encoding="utf-8")
    columns, _, rows = read_rows(path, "fx_rates")
    assert dict(zip(columns, rows[0][0])) == {"rate_date": "2026-01-01", "currency": "CHF", "rate_to_eur": "1.06"}
