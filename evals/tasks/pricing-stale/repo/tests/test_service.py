import unittest

from pricing.catalog import Catalog
from pricing.service import PriceService


class ServiceTest(unittest.TestCase):
    def test_get_price_converts_and_caches(self):
        svc = PriceService(Catalog({"tea": 1000}, {"EUR": 0.9}))
        self.assertEqual(svc.get_price("tea"), 1000)
        self.assertEqual(svc.get_price("tea", "EUR"), 900)
        svc.get_price("tea", "EUR")
        self.assertEqual(svc.cache.hits, 1)

    def test_update_is_visible(self):
        svc = PriceService(Catalog({"tea": 1000}))
        svc.get_price("tea")
        svc.set_price("tea", 1200)
        self.assertEqual(svc.get_price("tea"), 1200)
