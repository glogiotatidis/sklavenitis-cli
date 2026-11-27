"""Live checks against www.sklavenitis.gr.

Run with ``SKLAVENITIS_LIVE=1 pytest -m live``. These are read-only and do not
touch a cart or an account.
"""
from __future__ import annotations

import os

import pytest

from sklavenitis_cli.api import Api

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("SKLAVENITIS_LIVE") != "1",
                    reason="set SKLAVENITIS_LIVE=1 to hit the real site")
def test_search_returns_products() -> None:
    data = Api().search("gala", limit=5)
    assert data["count"] >= 1
    assert data["results"][0]["sku"].isdigit()
    assert data["results"][0]["name"]


@pytest.mark.skipif(os.environ.get("SKLAVENITIS_LIVE") != "1",
                    reason="set SKLAVENITIS_LIVE=1 to hit the real site")
def test_address_lookup_is_served() -> None:
    api = Api()
    candidates = api.address_search("Ερμού 1, Αθήνα")
    assert candidates
    details = api.address_details(candidates[0]["ID"], candidates[0]["Description"])
    assert details["ZipCodeServed"] is True
    assert details["Address"]["ZipCode"]
