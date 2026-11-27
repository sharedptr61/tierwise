"""Message formatting."""
from notify.settings import SETTINGS


def format_message(text):
    """Prefix the text and cut it to max_len characters, ending with an ellipsis when cut."""
    message = f"{SETTINGS['prefix']} {text.strip()}"
    if len(message) > SETTINGS["max_len"]:
        message = message[: SETTINGS["max_len"] - 1] + "…"
    return message
