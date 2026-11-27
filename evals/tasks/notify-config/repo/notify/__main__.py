"""python3 -m notify "text": format and send to standard output."""
import sys

from notify.formatter import format_message
from notify.sender import DeliveryError, send
from notify.settings import SETTINGS


def stdout_transport(message):
    print(message)
    return True


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python3 -m notify TEXT", file=sys.stderr)
        return 2
    message = format_message(" ".join(args))
    if SETTINGS["dry_run"]:
        print(f"{message} (dry run)")
        return 0
    try:
        send(message, stdout_transport)
    except DeliveryError as e:
        print(f"notify: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
