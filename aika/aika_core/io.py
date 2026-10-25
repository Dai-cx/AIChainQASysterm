"""Readers for the CSV and JSONL artifacts that back the knowledge base.

The same two formats were being decoded by hand in five and four places respectively,
each with its own blank-line handling, encoding and missing-file policy. Those differences
were accidental, so both shapes live here now.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def read_csv_rows(
    path: str | Path,
    *,
    missing_ok: bool = False,
    encoding: str = "utf-8",
) -> list[dict[str, str]]:
    """Read a CSV file as a list of header-keyed rows.

    ``newline=""`` is required for the csv module: without it, quoted values that contain
    a newline are split across records.
    """
    target = Path(path)
    if missing_ok and not target.exists():
        return []
    with target.open(newline="", encoding=encoding) as file:
        return list(csv.DictReader(file))


def read_jsonl_rows(
    path: str | Path,
    *,
    missing_ok: bool = False,
    encoding: str = "utf-8",
) -> list[Any]:
    """Read a JSON Lines file, skipping blank lines.

    Malformed JSON is deliberately not swallowed here: callers that want to report the
    bad line (the knowledge-pack validator) collect errors themselves.
    """
    target = Path(path)
    rows: list[Any] = []
    if missing_ok and not target.exists():
        return rows
    with target.open(encoding=encoding) as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl_row(path: str | Path, row: Any) -> None:
    """Append one object to a JSON Lines file, creating parents if needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
