"""Message formatting."""


def format_message(text, config):
    message = f"{config.prefix} {text.strip()}"
    if len(message) > config.max_len:
        message = message[: config.max_len - 1] + "…"
    return message
