"""Unit tests of the source data simulator (no database needed)."""
import csv
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from retail_pipeline.generate import CHANNEL_COLUMN_FROM_DAY, EXTRA_COLUMN_FROM_DAY, generate

START = date(2026, 1, 1)
DAYS = 62


@pytest.fixture(scope="module")
def landing(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("landing")
    generate(out, START, DAYS, n_stores=2, n_products=12, n_suppliers=3, seed=7)
    return out


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def all_rows(landing: Path, entity: str) -> list[dict]:
    rows = []
    for day_dir in sorted(landing.iterdir()):
        f = day_dir / f"{entity}.csv"
        if f.exists():
            for r in read(f):
                r["_batch"] = day_dir.name
                rows.append(r)
    return rows


def is_valid_sale(r: dict) -> bool:
    try:
        datetime.fromisoformat(r["sold_at"])
        return bool(r["sale_line_id"] and r["store_id"] and r["product_id"]) and int(r["quantity"]) > 0 \
            and float(r["unit_price"]) >= 0
    except (ValueError, TypeError):
        return False


def test_one_folder_per_day_with_manifest(landing):
    folders = sorted(p.name for p in landing.iterdir())
    assert len(folders) == DAYS
    assert all((landing / f / "_manifest.json").exists() for f in folders)


def test_manifest_matches_the_files(landing):
    for day_dir in landing.iterdir():
        manifest = json.loads((day_dir / "_manifest.json").read_text())
        for entity, entry in manifest["files"].items():
            rows = read(day_dir / f"{entity}.csv")
            assert entry["row_count"] == len(rows), (day_dir.name, entity)


def test_sales_have_realistic_values(landing):
    sales = [r for r in all_rows(landing, "sales") if is_valid_sale(r)]
    assert len(sales) > 1000
    for r in sales:
        assert 1 <= int(r["quantity"]) <= 3
        assert r["currency"] in ("EUR", "CHF")
        assert 0 < float(r["unit_price"]) < 200
        assert float(r["discount_amount"]) <= int(r["quantity"]) * float(r["unit_price"])


def test_ids_are_unique_except_injected_duplicates(landing):
    sales = [r for r in all_rows(landing, "sales") if r["sale_line_id"]]
    ids = [r["sale_line_id"] for r in sales]
    duplicates = len(ids) - len(set(ids))
    # a small share of exact duplicates is injected on purpose (about 0.5%)
    assert 0 < duplicates < len(ids) * 0.02


def test_data_problems_are_injected(landing):
    sales = all_rows(landing, "sales")
    invalid = [r for r in sales if not is_valid_sale(r)]
    late = [r for r in sales if is_valid_sale(r) and r["sold_at"][:10] < r["_batch"]]
    assert invalid, "some invalid rows are expected"
    assert late, "some late-arriving rows are expected"
    assert len(invalid) < len(sales) * 0.01


def test_schema_evolution_columns_appear_later(landing):
    first = read(landing / START.isoformat() / "sales.csv")[0]
    assert "channel" not in first
    later_day = date.fromordinal(START.toordinal() + EXTRA_COLUMN_FROM_DAY + 1).isoformat()
    header = next(csv.reader((landing / later_day / "sales.csv").open(encoding="utf-8")))
    assert "channel" in header and "loyalty_card" in header
    assert CHANNEL_COLUMN_FROM_DAY < EXTRA_COLUMN_FROM_DAY


def test_same_seed_gives_same_files(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a, START, 5, 2, 6, 2, seed=11)
    generate(b, START, 5, 2, 6, 2, seed=11)
    for f in (a / START.isoformat()).glob("*.csv"):
        assert f.read_text() == (b / START.isoformat() / f.name).read_text()


def test_deliveries_reference_known_order_lines(landing):
    po_ids = {r["po_line_id"] for r in all_rows(landing, "purchase_orders")}
    for d in all_rows(landing, "deliveries"):
        assert d["po_line_id"] in po_ids
