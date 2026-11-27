"""Orders: loading, validation and totals."""
import json
from dataclasses import dataclass

STATUSES = ("paid", "pending", "cancelled")


@dataclass(frozen=True)
class Order:
    id: int
    customer: str
    amount_cents: int
    status: str


def load_orders(path):
    """Read orders from a JSON list of objects. Raises OSError or ValueError on bad input."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError("orders file must contain a JSON list")
    orders = []
    for item in raw:
        status = item["status"]
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        orders.append(Order(int(item["id"]), str(item["customer"]), int(item["amount_cents"]), status))
    return orders


def total_cents(orders):
    """Sum of amounts of orders that are not cancelled."""
    return sum(o.amount_cents for o in orders if o.status != "cancelled")


def format_amount(cents):
    """12345 -> '123.45'; -5 -> '-0.05'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
