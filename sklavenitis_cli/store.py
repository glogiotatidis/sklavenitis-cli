"""Config and session storage under ``~/.config/sklavenitis-cli``.

Two files, both mode 0600:

    cookies.json   the site's own cookies (the whole session)
    config.json    delivery address and preferred slot, no credentials

Override the directory with ``SKLAVENITIS_CONFIG_DIR``, which is what the tests
do. Passwords are never written here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

CONFIG_DIR_ENV = "SKLAVENITIS_CONFIG_DIR"


class StoreError(RuntimeError):
    pass


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "sklavenitis-cli"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    except OSError as exc:
        raise StoreError(f"cannot write {path}: {exc}") from exc


def cookie_path() -> Path:
    return config_dir() / "cookies.json"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_cookies() -> list[dict[str, Any]]:
    data = _read_json(cookie_path(), [])
    return data if isinstance(data, list) else []


def save_cookies(cookies: list[dict[str, Any]]) -> None:
    _write_json(cookie_path(), cookies)


def load_config() -> dict[str, Any]:
    data = _read_json(config_path(), {})
    return data if isinstance(data, dict) else {}


def save_config(config: dict[str, Any]) -> None:
    _write_json(config_path(), config)


def get_address(config: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    cfg = config if config is not None else load_config()
    address = cfg.get("address")
    return address if isinstance(address, dict) and address.get("zip") else None


def set_address(address: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    cfg["address"] = address
    save_config(cfg)
    return cfg


def clear_address() -> dict[str, Any]:
    cfg = load_config()
    cfg.pop("address", None)
    cfg.pop("delivery", None)
    save_config(cfg)
    return cfg


def get_delivery(config: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    cfg = config if config is not None else load_config()
    slot = cfg.get("delivery")
    return slot if isinstance(slot, dict) and slot.get("start") else None


def set_delivery(slot: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    cfg["delivery"] = slot
    save_config(cfg)
    return cfg


def clear_delivery() -> dict[str, Any]:
    cfg = load_config()
    cfg.pop("delivery", None)
    save_config(cfg)
    return cfg
