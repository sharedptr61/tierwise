"""A small time-to-live cache with hit and miss counters."""
import time


class TTLCache:
    def __init__(self, ttl_seconds=600, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.clock = clock
        self._items = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        item = self._items.get(key)
        if item is None or item[1] <= self.clock():
            self._items.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return item[0]

    def set(self, key, value):
        self._items[key] = (value, self.clock() + self.ttl)

    def delete(self, key):
        self._items.pop(key, None)

    def keys(self):
        return list(self._items)
