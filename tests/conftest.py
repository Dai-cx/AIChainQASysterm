"""Shared pytest configuration for AIKA.

The only thing asserted here is *where* pytest is allowed to create temporary
directories.  On Windows the default location (`%TEMP%\\pytest-of-<user>`) is often
locked down by corporate policy, endpoint protection or a container sandbox, and every
test that touches `tmp_path` then fails with `PermissionError: [WinError 5]` — an
environment failure that looks exactly like a code failure.  Pinning the base temp
directory inside the checkout keeps the suite reproducible and makes those failures
disappear.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PYTEST_TMP = REPO_ROOT / ".tmp" / "pytest"


def pytest_configure(config) -> None:
    if getattr(config.option, "basetemp", None):
        return
    LOCAL_PYTEST_TMP.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(LOCAL_PYTEST_TMP)
