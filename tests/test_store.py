"""Config/cookie storage tests."""
from __future__ import annotations

import os
import stat

from sklavenitis_cli import store


def test_cookie_roundtrip_and_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(store.CONFIG_DIR_ENV, str(tmp_path))
    cookies = [{"name": "A", "value": "1", "domain": ".sklavenitis.gr", "path": "/",
                "secure": True, "expires": None}]
    store.save_cookies(cookies)
    assert store.load_cookies() == cookies
    mode = stat.S_IMODE(os.stat(store.cookie_path()).st_mode)
    assert mode == 0o600


def test_address_and_delivery_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(store.CONFIG_DIR_ENV, str(tmp_path))
    store.set_address({"label": "X", "zip": "10000"})
    assert store.get_address() == {"label": "X", "zip": "10000"}
    store.set_delivery({"start": "2026-11-28 07:00:00", "end": "2026-11-28 09:00:00"})
    assert store.get_delivery()["start"] == "2026-11-28 07:00:00"
    store.clear_address()
    assert store.get_address() is None
    assert store.get_delivery() is None
