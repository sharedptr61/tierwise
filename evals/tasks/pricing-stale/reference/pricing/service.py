"""The price service the shop front end calls."""
from pricing.cache import TTLCache
from pricing.catalog import convert


class PriceService:
    def __init__(self, catalog, cache=None):
        self.catalog = catalog
        self.cache = cache or TTLCache(ttl_seconds=600)

    def _key(self, sku, currency):
        return f"{sku}:{currency.upper()}"

    def get_price(self, sku, currency="USD"):
        """Price of sku in currency, in that currency's cents."""
        key = self._key(sku, currency)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rate = self.catalog.rates[currency.upper()]
        price = convert(self.catalog.base_cents(sku), rate)
        self.cache.set(key, price)
        return price

    def set_price(self, sku, cents):
        """Change the base price (US cents); callers must see it at once."""
        self.catalog.set_base_cents(sku, cents)
        for currency in self.catalog.rates:  # every cached currency of this product
            self.cache.delete(self._key(sku, currency))
