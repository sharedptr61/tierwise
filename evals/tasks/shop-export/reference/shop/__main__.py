"""Command line: python3 -m shop report <orders.json>"""
import argparse
import sys

from shop.orders import format_amount, load_orders, total_cents


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shop")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="print orders and the total")
    report.add_argument("orders")
    export = sub.add_parser("export", help="write orders to CSV")
    export.add_argument("orders")
    export.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        orders = load_orders(args.orders)
    except (OSError, ValueError) as e:
        print(f"shop: {e}", file=sys.stderr)
        return 1
    if args.command == "export":
        from shop.export import export_csv
        export_csv(orders, args.out)
        return 0
    for o in orders:
        print(f"{o.id:>5}  {o.customer:<20}  {format_amount(o.amount_cents):>10}  {o.status}")
    print(f"total: {format_amount(total_cents(orders))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
