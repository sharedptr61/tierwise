"""Hidden acceptance tests for shop-export. Not shown to the agent."""
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())


def run_export(orders, extra=()):
    d = tempfile.mkdtemp()
    src, out = os.path.join(d, "o.json"), os.path.join(d, "out.csv")
    with open(src, "w", encoding="utf-8") as f:
        json.dump(orders, f)
    p = subprocess.run([sys.executable, "-m", "shop", "export", src, "--out", out, *extra],
                       capture_output=True, text=True, cwd=os.getcwd())
    rows = None
    if os.path.exists(out):
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    return p, rows


ORDERS = [
    {"id": 1, "customer": "Ann", "amount_cents": 1999, "status": "paid"},
    {"id": 2, "customer": "Bob, Jr.", "amount_cents": 500, "status": "cancelled"},
    {"id": 3, "customer": "Cy \"The Guy\"", "amount_cents": 5, "status": "pending"},
    {"id": 4, "customer": "Line\nBreak", "amount_cents": 100000, "status": "paid"},
]


class Export(unittest.TestCase):
    def test_header_rows_order_and_amounts(self):
        p, rows = run_export(ORDERS)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(rows[0], ["id", "customer", "amount", "status"])
        self.assertEqual([r[0] for r in rows[1:5]], ["1", "2", "3", "4"])
        self.assertEqual([r[2] for r in rows[1:5]], ["19.99", "5.00", "0.05", "1000.00"])
        self.assertEqual([r[3] for r in rows[1:5]], ["paid", "cancelled", "pending", "paid"])

    def test_special_characters_round_trip(self):
        _, rows = run_export(ORDERS)
        self.assertEqual([r[1] for r in rows[1:5]], ["Ann", "Bob, Jr.", "Cy \"The Guy\"", "Line\nBreak"])

    def test_total_row_excludes_cancelled(self):
        _, rows = run_export(ORDERS)
        self.assertEqual(rows[-1], ["TOTAL", "", "1020.04", ""])
        self.assertEqual(len(rows), 6)

    def test_formula_injection_is_neutralised(self):
        orders = [{"id": i, "customer": c, "amount_cents": 1, "status": "paid"}
                  for i, c in enumerate(["=SUM(A1)", "+1", "-2+3", "@cmd", "Safe=Name"], 1)]
        _, rows = run_export(orders)
        self.assertEqual([r[1] for r in rows[1:6]], ["'=SUM(A1)", "'+1", "'-2+3", "'@cmd", "Safe=Name"])

    def test_empty_orders(self):
        p, rows = run_export([])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(rows, [["id", "customer", "amount", "status"], ["TOTAL", "", "0.00", ""]])

    def test_missing_file_and_bad_json_exit_1(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "out.csv")
        p = subprocess.run([sys.executable, "-m", "shop", "export", os.path.join(d, "nope.json"), "--out", out],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stderr.strip())
        bad = os.path.join(d, "bad.json")
        with open(bad, "w") as f:
            f.write("{not json")
        p = subprocess.run([sys.executable, "-m", "shop", "export", bad, "--out", out],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stderr.strip())

    def test_function_is_importable_and_used(self):
        from shop.export import export_csv
        from shop.orders import Order
        d = tempfile.mkdtemp()
        out = os.path.join(d, "x.csv")
        export_csv([Order(7, "Zed", 1234, "paid")], out)
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows, [["id", "customer", "amount", "status"], ["7", "Zed", "12.34", "paid"], ["TOTAL", "", "12.34", ""]])

    def test_report_still_works(self):
        d = tempfile.mkdtemp()
        src = os.path.join(d, "o.json")
        with open(src, "w") as f:
            json.dump(ORDERS[:1], f)
        p = subprocess.run([sys.executable, "-m", "shop", "report", src], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("total: 19.99", p.stdout)


if __name__ == "__main__":
    unittest.main()
