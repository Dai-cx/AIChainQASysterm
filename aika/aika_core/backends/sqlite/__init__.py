"""SQLite research index: schema, loading, querying and the backend itself.

The implementation lives in the modules next to this one; this file is the public face so
callers keep importing from a single place.

Layout:
    util     small value helpers (text coercion, dedupe, serialisation)
    schema   table definitions and schema creation
    query    SQL predicates, query expansion, row scoring
    rows     row-to-model conversion, card shaping
    index    build / inspect / load the index
    backend  SQLiteResearchBackend plus the aika-home path helpers
"""

from __future__ import annotations

from aika.aika_core.backends.sqlite.backend import (
    AIKA_HOME_ENV,
    DEFAULT_PROFILE,
    SQLiteResearchBackend,
    profile_index_path,
    profile_knowledge_dir,
    resolve_aika_home,
)
from aika.aika_core.backends.sqlite.index import (
    build_sqlite_index,
    inspect_sqlite_index,
    sqlite_fts_status,
)
from aika.aika_core.backends.sqlite.schema import SCHEMA_VERSION

__all__ = [
    "AIKA_HOME_ENV",
    "DEFAULT_PROFILE",
    "SCHEMA_VERSION",
    "SQLiteResearchBackend",
    "build_sqlite_index",
    "inspect_sqlite_index",
    "profile_index_path",
    "profile_knowledge_dir",
    "resolve_aika_home",
    "sqlite_fts_status",
]
