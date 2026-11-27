"""Delivery with retries."""


class DeliveryError(Exception):
    pass


def send(message, transport, config):
    if config.dry_run:
        return 0
    for attempt in range(1, config.retries + 1):
        if transport(message):
            return attempt
    raise DeliveryError(f"gave up after {config.retries} attempts")
