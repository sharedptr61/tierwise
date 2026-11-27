"""Base prices in US cents, and exchange rates."""


class Catalog:
    def __init__(self, prices=None, rates=None):
        self._prices = dict(prices or {})
        self.rates = {"USD": 1.0, **(rates or {})}

    def base_cents(self, sku):
        return self._prices[sku]

    def set_base_cents(self, sku, cents):
        self._prices[sku] = cents


def convert(cents, rate):
    """Convert cents at a rate, rounding half up to whole cents."""
    return int(cents * rate + 0.5)
