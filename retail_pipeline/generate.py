"""Simulated source systems for a small retail chain.

This script plays the role of the company's operational systems (catalog, point of
sale, stock counts, purchasing, goods receipt, finance). It simulates the business
day by day and writes, for every day, the files those systems would export:

    data/landing/2026-01-15/
        products.csv          catalog changes of the day (new products, price changes)
        suppliers.csv         supplier master data (first day + changes)
        stores.csv            store master data (first day + changes)
        sales.csv             till receipts, one row per receipt line
        inventory.csv         end-of-day stock count per store and product
        purchase_orders.csv   orders sent to suppliers
        deliveries.csv        goods received from suppliers
        fx_rates.csv          exchange rates to EUR
        _manifest.json        control totals written by the source (used for reconciliation)

To make the warehouse work realistic, the files contain on purpose some of the
problems seen in real projects:
  * late-arriving records (a sale exported 1 or 2 days after it happened)
  * early-arriving facts (a new product is sold before its catalog row arrives)
  * late catalog updates (a price change exported two days late)
  * exact duplicates (the same receipt line sent twice)
  * invalid values (missing ids, negative quantities, unreadable timestamps...)
  * schema evolution (new columns appear in the sales file during the period)

All data is synthetic. Running it twice with the same seed gives the same files.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from retail_pipeline.config import settings

log = logging.getLogger("generate")

# Reference lists used to build the fake company
CITIES = [
    ("Paris", "FR", "EUR", "Ile-de-France"),
    ("Lyon", "FR", "EUR", "Auvergne-Rhone-Alpes"),
    ("Limoges", "FR", "EUR", "Nouvelle-Aquitaine"),
    ("Bordeaux", "FR", "EUR", "Nouvelle-Aquitaine"),
    ("Bruxelles", "BE", "EUR", "Bruxelles-Capitale"),
    ("Geneve", "CH", "CHF", "Geneve"),
    ("Lille", "FR", "EUR", "Hauts-de-France"),
    ("Nantes", "FR", "EUR", "Pays de la Loire"),
    ("Lausanne", "CH", "CHF", "Vaud"),
    ("Liege", "BE", "EUR", "Wallonie"),
]
CATEGORIES = {
    "Grocery": (["Pasta", "Rice", "Snacks", "Canned food"], 1.0, 4.0),
    "Beverages": (["Water", "Juice", "Coffee", "Tea"], 0.8, 6.0),
    "Household": (["Cleaning", "Paper", "Laundry"], 2.0, 9.0),
    "Personal Care": (["Shampoo", "Soap", "Toothpaste"], 1.5, 8.0),
    "Electronics": (["Cables", "Batteries", "Headphones"], 5.0, 40.0),
    "Toys": (["Puzzles", "Board games", "Plush"], 4.0, 25.0),
    "Garden": (["Seeds", "Tools", "Pots"], 2.0, 20.0),
    "Stationery": (["Notebooks", "Pens", "Folders"], 0.8, 6.0),
}
BRANDS = ["Nordline", "Verdi", "Atelier B", "Solenne", "Kappa Home", "Riviera", "Maison Lys", "Optima"]
SUPPLIER_COUNTRIES = ["FR", "FR", "FR", "BE", "DE", "ES", "IT", "NL"]

# Share of records affected by each data problem (kept small, like in real life)
LATE_SALE_RATE = 0.02          # sale exported 1-2 days late
DUPLICATE_RATE = 0.005         # receipt line sent twice
INVALID_SALE_RATE = 0.003      # receipt line with a broken field
LATE_STORE_INVENTORY_RATE = 0.01  # a whole store stock file arrives one day late
SHRINKAGE_RATE = 0.0005        # unexplained stock loss (simulated, for the anomaly indicator)
PRICE_ERROR_RATE = 0.001       # till price very different from the catalog price
# How many days of sales a store tries to keep in stock after a delivery.
# Slow, expensive categories keep more cover than fast-moving food.
TARGET_COVER_DAYS = {
    "Grocery": 12, "Beverages": 12, "Household": 22, "Personal Care": 22,
    "Electronics": 40, "Toys": 35, "Garden": 30, "Stationery": 25,
}
CHANNEL_COLUMN_FROM_DAY = 45   # schema evolution 1: new "channel" column
EXTRA_COLUMN_FROM_DAY = 60     # schema evolution 2: a column the warehouse does not know


@dataclass
class Product:
    product_id: str
    sku: str
    name: str
    category: str
    subcategory: str
    brand: str
    supplier_id: str
    unit_cost: float
    unit_price: float
    popularity: float          # mean units sold per store per day
    launch_day: int            # 0 = exists from the first day
    is_active: bool = True


@dataclass
class Supplier:
    supplier_id: str
    name: str
    country: str
    city: str
    promised_lead_time: int
    on_time_prob: float        # hidden "true" reliability used by the simulation
    in_full_prob: float


@dataclass
class OpenOrderLine:
    po_line_id: str
    store_id: str
    product_id: str
    qty_left: int              # quantity still expected from the supplier


@dataclass
class SimulationState:
    on_hand: dict = field(default_factory=dict)       # (store, product) -> units
    on_order: dict = field(default_factory=lambda: defaultdict(int))
    scheduled_deliveries: dict = field(default_factory=lambda: defaultdict(list))  # day -> [(po_line, qty)]
    open_lines: dict = field(default_factory=dict)    # po_line_id -> OpenOrderLine


def build_master_data(rng: np.random.Generator, n_stores: int, n_products: int, n_suppliers: int, days: int):
    """Create the stores, suppliers and product catalog of the fake company."""
    stores = []
    for i in range(n_stores):
        city, country, currency, region = CITIES[i % len(CITIES)]
        suffix = "" if i < len(CITIES) else f" {i // len(CITIES) + 1}"
        stores.append({
            "store_id": f"S{i + 1:02d}",
            "store_name": f"Retail {city}{suffix}",
            "city": city,
            "country": country,
            "currency": currency,
            "region": region,
            "size_factor": round(float(rng.uniform(0.7, 1.4)), 2),  # big stores sell more
            "manager_name": f"Manager {i + 1:02d}",
        })

    suppliers = []
    for i in range(n_suppliers):
        suppliers.append(Supplier(
            supplier_id=f"SUP{i + 1:02d}",
            name=f"Supplier {chr(65 + i % 26)}{i // 26 or ''} SARL",
            country=SUPPLIER_COUNTRIES[i % len(SUPPLIER_COUNTRIES)],
            city=f"City {i + 1}",
            promised_lead_time=int(rng.integers(3, 9)),
            on_time_prob=float(rng.uniform(0.55, 0.97)),
            in_full_prob=float(rng.uniform(0.75, 0.99)),
        ))

    products = []
    category_names = list(CATEGORIES)
    for i in range(n_products):
        category = category_names[i % len(category_names)]
        subcats, low, high = CATEGORIES[category]
        cost = round(float(rng.uniform(low, high)), 2)
        # About 10% of products are launched during the period (new products)
        launch_day = int(rng.integers(5, max(6, days - 10))) if rng.random() < 0.10 else 0
        products.append(Product(
            product_id=f"P{i + 1:04d}",
            sku=f"SKU-{100000 + i}",
            name=f"{rng.choice(BRANDS)} {rng.choice(subcats)} {i + 1}",
            category=category,
            subcategory=str(rng.choice(subcats)),
            brand=str(rng.choice(BRANDS)),
            supplier_id=suppliers[int(rng.integers(0, n_suppliers))].supplier_id,
            unit_cost=cost,
            unit_price=round(cost * float(rng.uniform(1.3, 1.9)), 2),
            popularity=float(rng.gamma(2.0, 1.2)) + 0.2,
            launch_day=launch_day,
        ))
    return stores, suppliers, products


def product_row(p: Product, updated_at: datetime) -> dict:
    return {
        "product_id": p.product_id, "sku": p.sku, "product_name": p.name,
        "category": p.category, "subcategory": p.subcategory, "brand": p.brand,
        "supplier_id": p.supplier_id, "unit_cost": f"{p.unit_cost:.2f}",
        "unit_price": f"{p.unit_price:.2f}", "currency": "EUR",
        "is_active": str(p.is_active).lower(), "updated_at": updated_at.isoformat(sep=" "),
    }


def supplier_row(s: Supplier, updated_at: datetime) -> dict:
    return {
        "supplier_id": s.supplier_id, "supplier_name": s.name, "country": s.country,
        "city": s.city, "promised_lead_time_days": s.promised_lead_time,
        "updated_at": updated_at.isoformat(sep=" "),
    }


def store_row(s: dict, updated_at: datetime) -> dict:
    row = {k: v for k, v in s.items() if k != "size_factor"}
    row["updated_at"] = updated_at.isoformat(sep=" ")
    return row


def corrupt_sale(row: dict, rng: np.random.Generator) -> dict:
    """Break one field of a receipt line, the way a buggy till export would."""
    row = dict(row)
    problem = int(rng.integers(0, 7))
    if problem == 0:
        row["sale_line_id"] = ""                  # missing mandatory id
    elif problem == 1:
        row["store_id"] = ""                      # missing store
    elif problem == 2:
        row["quantity"] = str(int(rng.choice([0, -1, -3])))  # impossible quantity
    elif problem == 3:
        row["quantity"] = "two"                   # not a number
    elif problem == 4:
        row["sold_at"] = str(rng.choice(["N/A", "", "31/13/2026 25:61"]))  # unreadable timestamp
    elif problem == 5:
        row["unit_price"] = "-" + row["unit_price"]  # negative price
    else:
        row["product_id"] = ""                    # missing product
    return row


def generate(
    out_dir: Path,
    start: date,
    days: int,
    n_stores: int,
    n_products: int,
    n_suppliers: int,
    seed: int,
    clean: bool = True,
) -> dict:
    """Simulate `days` days of business and write one folder of files per day.

    Returns a small summary (number of rows per file type) used by tests and benchmarks.
    """
    rng = np.random.default_rng(seed)
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stores, suppliers, products = build_master_data(rng, n_stores, n_products, n_suppliers, days)
    supplier_by_id = {s.supplier_id: s for s in suppliers}
    store_by_id = {s["store_id"]: s for s in stores}

    # Planned catalog changes: price changes (SCD2) and a few supplier switches
    price_changes = {}   # day -> list of products
    for p in products:
        first_possible = max(p.launch_day + 3, 10)
        if rng.random() < 0.15 and first_possible < days:   # short simulations have no price change
            day = int(rng.integers(first_possible, days))
            price_changes.setdefault(day, []).append(p)

    # Files are "delivered" on a given day; late rows are pushed to a later day
    outbox: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    state = SimulationState()
    fx_chf = 1.06            # 1 CHF = 1.06 EUR at the start, then a small random walk
    sale_counter = 0
    po_counter = 0
    delivery_counter = 0
    first_ts = datetime.combine(start, datetime.min.time())

    # Day 0: full extract of the master data
    outbox[0]["stores"] = [store_row(s, first_ts) for s in stores]
    outbox[0]["suppliers"] = [supplier_row(s, first_ts) for s in suppliers]
    outbox[0]["products"] = [product_row(p, first_ts) for p in products if p.launch_day == 0]

    for d in range(days):
        today = start + timedelta(days=d)
        day_ts = datetime.combine(today, datetime.min.time())
        weekday_factor = 1.35 if today.weekday() >= 5 else 1.0
        fx_chf = round(fx_chf * float(np.exp(rng.normal(0, 0.003))), 4)
        outbox[d]["fx_rates"] += [
            {"rate_date": today.isoformat(), "currency": "EUR", "rate_to_eur": "1.0000"},
            {"rate_date": today.isoformat(), "currency": "CHF", "rate_to_eur": f"{fx_chf:.4f}"},
        ]

        # --- catalog events of the day ---------------------------------------
        for p in products:
            if p.launch_day == d and d > 0:
                # New product: half of the time the catalog export is one day late,
                # so the first sales arrive before the product (early-arriving fact).
                delay = 1 if rng.random() < 0.5 else 0
                outbox[d + delay]["products"].append(product_row(p, day_ts + timedelta(hours=6)))
                for s in stores:  # first stock for the launch
                    state.on_hand[(s["store_id"], p.product_id)] = int(p.popularity * 12) + 5
        for p in price_changes.get(d, []):
            p.unit_price = round(p.unit_price * float(rng.choice([0.85, 0.9, 1.08, 1.12, 1.2])), 2)
            p.unit_cost = round(p.unit_cost * float(rng.uniform(0.97, 1.06)), 2)
            if rng.random() < 0.2:  # sometimes the product also moves to another supplier
                p.supplier_id = suppliers[int(rng.integers(0, n_suppliers))].supplier_id
            delay = 2 if rng.random() < 0.15 else 0   # late catalog update
            outbox[d + delay]["products"].append(product_row(p, day_ts + timedelta(hours=5)))
        # Master data changes that are simply overwritten in the warehouse (SCD type 1)
        if d == days // 2 and stores:
            s = stores[0]
            s["manager_name"] = "Manager 99"
            outbox[d]["stores"].append(store_row(s, day_ts + timedelta(hours=7)))
        if d == days // 3 and suppliers:
            sup = suppliers[0]
            sup.name = sup.name.replace("SARL", "SAS")
            outbox[d]["suppliers"].append(supplier_row(sup, day_ts + timedelta(hours=7)))

        # --- deliveries arriving this morning -----------------------------------
        for po_line_id, qty in state.scheduled_deliveries.pop(d, []):
            line = state.open_lines[po_line_id]
            key = (line.store_id, line.product_id)
            state.on_hand[key] = state.on_hand.get(key, 0) + qty
            state.on_order[key] -= qty
            line.qty_left -= qty
            delivery_counter += 1
            outbox[d]["deliveries"].append({
                "delivery_id": f"D{delivery_counter:08d}", "po_line_id": po_line_id,
                "store_id": line.store_id, "received_date": today.isoformat(),
                "qty_received": str(qty),
            })

        # --- sales and end-of-day stock -----------------------------------------
        late_store = stores[int(rng.integers(0, n_stores))]["store_id"] if rng.random() < LATE_STORE_INVENTORY_RATE * n_stores else None
        # One category is on promotion each Saturday (rotation), which creates demand peaks
        promo_category = list(CATEGORIES)[(d // 7) % len(CATEGORIES)]
        for s in stores:
            sid = s["store_id"]
            for p in products:
                if p.launch_day > d:
                    continue
                key = (sid, p.product_id)
                if key not in state.on_hand:
                    # stores do not all start full: a random share of the target stock
                    state.on_hand[key] = int(p.popularity * TARGET_COVER_DAYS[p.category] * float(rng.uniform(0.6, 1.0))) + 2
                promo = 1.6 if (p.category == promo_category and today.weekday() == 5) else 1.0
                demand = int(rng.poisson(p.popularity * s["size_factor"] * weekday_factor * promo))
                sold = min(demand, state.on_hand[key])
                state.on_hand[key] -= sold

                # Split the units sold into receipt lines of 1 to 3 units
                local_price = p.unit_price if s["currency"] == "EUR" else round(p.unit_price / fx_chf, 2)
                while sold > 0:
                    qty = min(sold, int(rng.integers(1, 4)))
                    sold -= qty
                    sale_counter += 1
                    price = local_price
                    if rng.random() < PRICE_ERROR_RATE:
                        price = round(price * float(rng.choice([0.4, 2.5])), 2)
                    sold_at = day_ts + timedelta(seconds=int(rng.integers(8 * 3600, 21 * 3600)))
                    row = {
                        "sale_line_id": f"SL{sale_counter:09d}",
                        "receipt_id": f"R{sid}{d:04d}{int(rng.integers(0, 400)):04d}",
                        "store_id": sid, "product_id": p.product_id,
                        "sold_at": sold_at.isoformat(sep=" "), "quantity": str(qty),
                        "unit_price": f"{price:.2f}",
                        "discount_amount": f"{round(qty * price * 0.1, 2):.2f}" if rng.random() < 0.08 else "0.00",
                        "currency": s["currency"],
                    }
                    if d >= CHANNEL_COLUMN_FROM_DAY:
                        row["channel"] = str(rng.choice(["store", "store", "store", "click_collect"]))
                    if d >= EXTRA_COLUMN_FROM_DAY:
                        row["loyalty_card"] = "yes" if rng.random() < 0.3 else "no"
                    if rng.random() < INVALID_SALE_RATE:
                        row = corrupt_sale(row, rng)
                    # Late export: the line is written in a later day's file
                    delay = int(rng.choice([1, 2])) if rng.random() < LATE_SALE_RATE else 0
                    outbox[d + delay]["sales"].append(row)
                    if rng.random() < DUPLICATE_RATE:
                        outbox[d + int(rng.choice([0, 1]))]["sales"].append(dict(row))

                # Simulated unexplained stock loss (feeds the shrinkage indicator)
                if state.on_hand[key] > 3 and rng.random() < SHRINKAGE_RATE:
                    state.on_hand[key] -= int(rng.integers(2, min(7, state.on_hand[key])))

                inv_row = {
                    "snapshot_date": today.isoformat(), "store_id": sid,
                    "product_id": p.product_id, "on_hand_qty": str(state.on_hand[key]),
                }
                outbox[d + (1 if sid == late_store else 0)]["inventory"].append(inv_row)

                # --- replenishment: simple reorder-point policy -------------------
                sup = supplier_by_id[p.supplier_id]
                daily = p.popularity * s["size_factor"]
                reorder_point = daily * (sup.promised_lead_time + 2)
                position = state.on_hand[key] + state.on_order[key]
                if position <= reorder_point:
                    qty = max(1, int(round(daily * (sup.promised_lead_time + TARGET_COVER_DAYS[p.category]) - position)))
                    po_counter += 1
                    po_line_id = f"POL{po_counter:08d}"
                    promised = today + timedelta(days=sup.promised_lead_time)
                    outbox[d]["purchase_orders"].append({
                        "po_line_id": po_line_id, "po_id": f"PO{d:04d}{sup.supplier_id}",
                        "supplier_id": sup.supplier_id, "store_id": sid,
                        "product_id": p.product_id, "order_date": today.isoformat(),
                        "promised_date": promised.isoformat(), "qty_ordered": str(qty),
                        "unit_cost": f"{p.unit_cost:.2f}",
                    })
                    state.on_order[key] += qty
                    state.open_lines[po_line_id] = OpenOrderLine(po_line_id, sid, p.product_id, qty)
                    # When will the supplier really deliver, and how much?
                    lead = sup.promised_lead_time
                    if rng.random() > sup.on_time_prob:
                        lead += int(rng.integers(1, 6))          # late delivery
                    elif rng.random() < 0.1:
                        lead -= 1                                # slightly early
                    first_qty = qty
                    if rng.random() > sup.in_full_prob:
                        first_qty = max(1, int(qty * float(rng.uniform(0.5, 0.9))))  # partial delivery
                        if rng.random() < 0.5:                   # the rest comes a few days later
                            state.scheduled_deliveries[d + lead + int(rng.integers(2, 5))].append((po_line_id, qty - first_qty))
                        else:                                    # the rest never comes
                            state.on_order[key] -= qty - first_qty
                    state.scheduled_deliveries[d + max(1, lead)].append((po_line_id, first_qty))

    # A few deliveries with a broken quantity (to test the delivery quality rules)
    for d in range(days):
        for row in outbox[d]["deliveries"]:
            if rng.random() < 0.002:
                row["qty_received"] = "-" + row["qty_received"]

    return write_outbox(out_dir, start, days, outbox)


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_manifest(files: dict[str, list]) -> dict:
    """Control totals computed by the 'source system' on exactly what it exported.

    The warehouse later checks that it loaded the same number of rows and the same
    sums (see retail_pipeline/reconcile.py).
    """
    measure = {
        "sales": "quantity", "inventory": "on_hand_qty",
        "purchase_orders": "qty_ordered", "deliveries": "qty_received",
    }
    manifest = {}
    for name, rows in files.items():
        entry = {"row_count": len(rows)}
        col = measure.get(name)
        if col:
            values = [_to_float(r.get(col)) for r in rows]
            entry["sum_" + col] = round(sum(v for v in values if v is not None), 2)
        manifest[name] = entry
    return manifest


def write_outbox(out_dir: Path, start: date, days: int, outbox) -> dict:
    """Write each day's files plus its manifest. Rows pushed after the last day are dropped
    (in reality they would arrive in the next, not yet simulated, export)."""
    summary = defaultdict(int)
    for d in range(days):
        day_dir = out_dir / (start + timedelta(days=d)).isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        files = outbox.get(d, {})
        for name, rows in files.items():
            if not rows:
                continue
            # Column order = union of keys in order of first appearance (schema can grow)
            columns = list(dict.fromkeys(k for r in rows for k in r))
            pd.DataFrame(rows, columns=columns).to_csv(day_dir / f"{name}.csv", index=False)
            summary[name] += len(rows)
        manifest = {
            "batch_date": (start + timedelta(days=d)).isoformat(),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "files": build_manifest({k: v for k, v in files.items() if v}),
        }
        (day_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dict(summary)


def main_from_settings() -> dict:
    """Generate the source files with the values of the configuration (.env)."""
    summary = generate(settings.landing_dir, settings.start_date, settings.days, settings.n_stores,
                       settings.n_products, settings.n_suppliers, settings.seed)
    log.info("Generated files in %s: %s", settings.landing_dir, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic retail source files")
    parser.add_argument("--start", default=settings.start_date.isoformat())
    parser.add_argument("--days", type=int, default=settings.days)
    parser.add_argument("--stores", type=int, default=settings.n_stores)
    parser.add_argument("--products", type=int, default=settings.n_products)
    parser.add_argument("--suppliers", type=int, default=settings.n_suppliers)
    parser.add_argument("--seed", type=int, default=settings.seed)
    parser.add_argument("--out", default=str(settings.landing_dir))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    summary = generate(Path(args.out), date.fromisoformat(args.start), args.days,
                       args.stores, args.products, args.suppliers, args.seed)
    log.info("Generated files in %s: %s", args.out, summary)


if __name__ == "__main__":
    main()
