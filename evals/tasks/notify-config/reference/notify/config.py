"""Explicit configuration (reference solution for the evaluation; not shown to agents)."""
from dataclasses import dataclass

TRUE = ("1", "true", "yes")


@dataclass(frozen=True)
class Config:
    prefix: str = "[notify]"
    max_len: int = 140
    retries: int = 3
    dry_run: bool = False

    @classmethod
    def from_env(cls, environ):
        d = cls()
        return cls(
            prefix=environ.get("NOTIFY_PREFIX", d.prefix),
            max_len=int(environ.get("NOTIFY_MAX_LEN", d.max_len)),
            retries=int(environ.get("NOTIFY_RETRIES", d.retries)),
            dry_run=environ.get("NOTIFY_DRY_RUN", "").lower() in TRUE,
        )
