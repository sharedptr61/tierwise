"""Hidden acceptance tests for pricing-stale. Not shown to the agent."""
import os
import sys
import unittest

sys.path.insert(0, os.getcwd())

from pricing.cache import TTLCache  # noqa: E402
from pricing.catalog import Catalog  # noqa: E402
from pricing.service import PriceService  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def service(clock=None):
    clock = clock or Clock()
    cache = TTLCache(ttl_seconds=600, clock=clock)
    return PriceService(Catalog({"tea": 1000, "mug": 500}, {"EUR": 0.9, "GBP": 0.8}), cache), clock


class Stale(unittest.TestCase):
    def test_update_visible_in_every_currency_at_once(self):
        svc, _ = service()
        for cur in ("USD", "EUR", "GBP", "eur"):
            svc.get_price("tea", cur)
        svc.set_price("tea", 2000)
        self.assertEqual(svc.get_price("tea", "USD"), 2000)
        self.assertEqual(svc.get_price("tea", "EUR"), 1800)
        self.assertEqual(svc.get_price("tea", "eur"), 1800)
        self.assertEqual(svc.get_price("tea", "GBP"), 1600)

    def test_cache_still_used_after_fix(self):
        svc, _ = service()
        svc.get_price("tea", "EUR")
        svc.set_price("tea", 2000)
        svc.get_price("tea", "EUR")
        hits = svc.cache.hits
        svc.get_price("tea", "EUR")
        self.assertEqual(svc.cache.hits, hits + 1, "repeat lookups must still be served from the cache")

    def test_other_products_keep_their_cache(self):
        svc, _ = service()
        svc.get_price("mug", "EUR")
        svc.set_price("tea", 2000)
        hits = svc.cache.hits
        self.assertEqual(svc.get_price("mug", "EUR"), 450)
        self.assertEqual(svc.cache.hits, hits + 1, "changing tea must not drop mug from the cache")

    def test_ttl_unchanged(self):
        svc, clock = service()
        self.assertEqual(svc.cache.ttl, 600)
        self.assertEqual(PriceService(Catalog({"x": 1})).cache.ttl, 600)
        svc.get_price("tea", "EUR")
        clock.t += 599
        hits = svc.cache.hits
        svc.get_price("tea", "EUR")
        self.assertEqual(svc.cache.hits, hits + 1)

    def test_currency_case_is_one_entry(self):
        svc, _ = service()
        svc.get_price("tea", "eur")
        hits = svc.cache.hits
        svc.get_price("tea", "EUR")
        self.assertEqual(svc.cache.hits, hits + 1)


if __name__ == "__main__":
    unittest.main()
