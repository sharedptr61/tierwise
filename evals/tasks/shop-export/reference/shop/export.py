"""CSV export of orders (reference solution for the evaluation; not shown to agents)."""
import csv

from shop.orders import format_amount, total_cents

FORMULA_START = ("=", "+", "-", "@")


def safe_cell(value):
    return "'" + value if value.startswith(FORMULA_START) else value


def export_csv(orders, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "customer", "amount", "status"])
        for o in orders:
            w.writerow([o.id, safe_cell(o.customer), format_amount(o.amount_cents), o.status])
        w.writerow(["TOTAL", "", format_amount(total_cents(orders)), ""])
