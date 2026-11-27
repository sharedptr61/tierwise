"""Delivery with retries."""
from notify.settings import SETTINGS


class DeliveryError(Exception):
    pass


def send(message, transport):
    """Send through transport(message) -> bool, trying up to `retries` times. Returns the attempts used."""
    if SETTINGS["dry_run"]:
        return 0
    for attempt in range(1, SETTINGS["retries"] + 1):
        if transport(message):
            return attempt
    raise DeliveryError(f"gave up after {SETTINGS['retries']} attempts")
