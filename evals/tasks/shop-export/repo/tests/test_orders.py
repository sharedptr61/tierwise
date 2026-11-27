import json
import os
import subprocess
import sys
import tempfile
import unittest

from shop.orders import Order, format_amount, load_orders, total_cents


class OrdersTest(unittest.TestCase):
    def test_total_excludes_cancelled(self):
        orders = [Order(1, "a", 1000, "paid"), Order(2, "b", 500, "cancelled"), Order(3, "c", 250, "pending")]
        self.assertEqual(total_cents(orders), 1250)

    def test_format_amount(self):
        self.assertEqual(format_amount(12345), "123.45")
        self.assertEqual(format_amount(5), "0.05")

    def test_report_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "o.json")
            with open(path, "w") as f:
                json.dump([{"id": 1, "customer": "Ann", "amount_cents": 1999, "status": "paid"}], f)
            out = subprocess.run([sys.executable, "-m", "shop", "report", path], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertIn("total: 19.99", out.stdout)
