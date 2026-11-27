Refactor the notify package so its configuration is explicit instead of a global.

- Replace the module-level `SETTINGS` dictionary with a frozen dataclass `Config` in `notify/config.py`, with fields `prefix: str = "[notify]"`, `max_len: int = 140`, `retries: int = 3`, `dry_run: bool = False`.
- Add `Config.from_env(environ)`, which reads `NOTIFY_PREFIX`, `NOTIFY_MAX_LEN`, `NOTIFY_RETRIES` and `NOTIFY_DRY_RUN` from the given mapping (`"1"`, `"true"`, `"yes"` in any case mean true), using the defaults for anything missing.
- `format_message(text, config)` and `send(message, transport, config)` take the configuration explicitly. The command line builds one `Config` from `os.environ` and passes it down.
- Delete `notify/settings.py`; nothing may keep module-level configuration state.
- Behaviour must not change. Update the tests to the new interface.

Make reasonable decisions yourself; do not stop to ask me.
