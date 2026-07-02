from __future__ import annotations
from pathlib import Path
from typing import Any
import os
import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # Keep app bootable if python-dotenv is not installed yet.
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]


def _load_env_file() -> None:
    env_path = ROOT / '.env'
    if load_dotenv:
        load_dotenv(env_path)
        return

    # Minimal fallback parser for KEY=value lines.
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file()


def load_config() -> dict[str, Any]:
    path = ROOT / 'config.yaml'
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def root_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts).resolve()


def get_absolute_db_path(cfg: dict | None = None) -> str:
    """Return project-root anchored SQLite path. Safe under Passenger/Cron CWD changes."""
    cfg = cfg or {}
    candidates = [
        cfg.get('database', {}).get('path') if isinstance(cfg.get('database'), dict) else None,
        cfg.get('database_path'),
        cfg.get('storage', {}).get('database_path') if isinstance(cfg.get('storage'), dict) else None,
        cfg.get('storage', {}).get('db_path') if isinstance(cfg.get('storage'), dict) else None,
        'data/btc_radar.db',
    ]
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate))
            return str(path if path.is_absolute() else root_path(str(candidate)))
    return str(root_path('data/btc_radar.db'))


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def env_value(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)
