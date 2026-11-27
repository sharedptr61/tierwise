"""python3 -m notify "text": format and send to standard output."""
import os
import sys

from notify.config import Config
from notify.formatter import format_message
from notify.sender import DeliveryError, send


def stdout_transport(message):
    print(message)
    return True


def main(argv=None, environ=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python3 -m notify TEXT", file=sys.stderr)
        return 2
    config = Config.from_env(os.environ if environ is None else environ)
    message = format_message(" ".join(args), config)
    if config.dry_run:
        print(f"{message} (dry run)")
        return 0
    try:
        send(message, stdout_transport, config)
    except DeliveryError as e:
        print(f"notify: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
