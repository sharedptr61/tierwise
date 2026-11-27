"""Configuration, read from the environment when the module is imported."""
import os

SETTINGS = {
    "prefix": os.environ.get("NOTIFY_PREFIX", "[notify]"),
    "max_len": int(os.environ.get("NOTIFY_MAX_LEN", "140")),
    "retries": int(os.environ.get("NOTIFY_RETRIES", "3")),
    "dry_run": os.environ.get("NOTIFY_DRY_RUN", "").lower() in ("1", "true", "yes"),
}
