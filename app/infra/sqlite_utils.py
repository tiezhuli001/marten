from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path


SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000
FALLBACK_DIR_NAME = "marten"


def ensure_writable_parent(path: Path) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError:
        fallback_root = Path(tempfile.gettempdir()) / FALLBACK_DIR_NAME
        fallback_root.mkdir(parents=True, exist_ok=True)
        return fallback_root / path.name


def ensure_writable_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError:
        fallback_root = Path(tempfile.gettempdir()) / FALLBACK_DIR_NAME
        fallback_root.mkdir(parents=True, exist_ok=True)
        fallback_dir = fallback_root / path.name
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return connection
