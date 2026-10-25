"""Storage backends for AIKA Core.

The three backends have very different dependency footprints: the SQLite backend needs
only the standard library, the CSV backend pulls the whole research/QA stack, and the
Postgres backend needs psycopg. Importing them eagerly here meant that
``import aika.aika_core.backends.sqlite_backend`` also executed the CSV backend, and a
clean install without the optional dependencies failed with
``ModuleNotFoundError: No module named 'jinja2'`` before any code ran.

Names are therefore resolved on first access.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CSVResearchBackend", "PostgresResearchBackend", "SQLiteResearchBackend"]

_BACKENDS = {
    "CSVResearchBackend": "aika.aika_core.backends.csv_backend",
    "PostgresResearchBackend": "aika.aika_core.backends.postgres_backend",
    "SQLiteResearchBackend": "aika.aika_core.backends.sqlite_backend",
}


def __getattr__(name: str) -> Any:
    module_path = _BACKENDS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_path), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
