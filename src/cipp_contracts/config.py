from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def database_url(explicit: str | None = None, env_path: Path | None = None) -> str:
    if explicit:
        return explicit
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if env_path:
        values = load_env_file(env_path)
        if values.get("DATABASE_URL"):
            return values["DATABASE_URL"]
    raise ValueError("Database URL missing. Use --db, DATABASE_URL, or .env with DATABASE_URL.")

