"""Generates a small synthetic sales dataset so the agent has something to query
out of the box. Pure stdlib, deterministic (fixed seed) so the output is
reproducible and diffable if regenerated."""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

REGIONS = ["North", "South", "East", "West"]
REGION_WEIGHTS = [0.3, 0.25, 0.25, 0.2]
PRODUCT_CATEGORIES = {
    "Widget": "Hardware",
    "Gadget": "Hardware",
    "Gizmo": "Electronics",
    "Doohickey": "Electronics",
    "Thingamajig": "Accessories",
}
START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)
DAY_SPAN = (END_DATE - START_DATE).days


def generate_rows(n_rows: int = 2000) -> list[dict]:
    rows = []
    for order_id in range(1, n_rows + 1):
        order_date = START_DATE + timedelta(days=random.randint(0, DAY_SPAN))
        region = random.choices(REGIONS, weights=REGION_WEIGHTS, k=1)[0]
        product = random.choice(list(PRODUCT_CATEGORIES))
        quantity = random.randint(1, 20)
        unit_price = round(random.uniform(5, 250), 2)
        rows.append(
            {
                "order_id": order_id,
                "order_date": order_date.isoformat(),
                "region": region,
                "product": product,
                "category": PRODUCT_CATEGORIES[product],
                "quantity": quantity,
                "unit_price": unit_price,
                "revenue": round(quantity * unit_price, 2),
                "customer_id": random.randint(1000, 1199),
            }
        )
    return rows


def main():
    rows = generate_rows()
    out_path = Path(__file__).parent / "sample_sales.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
