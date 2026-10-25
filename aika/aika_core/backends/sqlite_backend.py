"""Backwards-compatible import surface for the SQLite backend.

The implementation moved into :mod:`aika.aika_core.backends.sqlite`; this module stays so
the CLI, the MCP tools and the tests keep their existing imports.
"""

from __future__ import annotations

from aika.aika_core.backends.sqlite import (
    AIKA_HOME_ENV,
    DEFAULT_PROFILE,
    SCHEMA_VERSION,
    SQLiteResearchBackend,
    build_sqlite_index,
    inspect_sqlite_index,
    profile_index_path,
    profile_knowledge_dir,
    resolve_aika_home,
    sqlite_fts_status,
)

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
