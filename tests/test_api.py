"""Offline tests for the cart wizard and payloads, with a scripted session."""
from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from sklavenitis_cli import api, _http, store

SLOT_HTML = """
<form id="promptslotselection">
  <input type="hidden" name="RequiresNotification" value="True" />
  <input type="hidden" name="Notification" value="some products may differ" />
  <div class="date__hours">
    <div class="date__box date__hour date__disabled hours_4"></div>
    <div class="date__box date__hour hours_14"
         data-starttime="2026-11-28 07:00:00"
         data-endtime="2026-11-28 09:00:00"
         data-display="Σάββατο 28 Νοεμβρίου 2026, 07:00 - 09:00"></div>
    <div class="date__box date__hour hours_14"
         data-starttime="2026-11-28 09:00:00"
         data-endtime="2026-11-28 11:00:00"
         data-display="Σάββατο 28 Νοεμβρίου 2026, 09:00 - 11:00"></div>
  </div>
</form>
"""

ADDRESS = {
    "label": "TEST STREET 1, TEST CITY, Ελλάδα",
    "street": "TEST STREET",
    "number": "1",
    "location": "TEST CITY",
    "state": "Αττική",
    "country": "Ελλάδα",
    "zip": "10000",
    "latitude": 37.9755972,
    "longitude": 23.7335539,
}


class FakeSession:
    def __init__(self, responses: list[_http.Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, Any, dict[str, Any]]] = []

    def _next(self) -> _http.Response:
        if not self.responses:
            raise AssertionError("FakeSession ran out of responses")
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> _http.Response:
        self.calls.append(("GET", url, None, kwargs))
        return self._next()

    def post(self, url: str, form: Optional[dict[str, Any]] = None,
             **kwargs: Any) -> _http.Response:
        self.calls.append(("POST", url, form, kwargs))
        return self._next()

    def cookie(self, name: str) -> Optional[str]:
        return None


def html(body: str) -> _http.Response:
    return _http.Response(200, {"content-type": "text/html; charset=utf-8"}, body, api.ADD_URL)


def made(**payload: Any) -> _http.Response:
    return _http.Response(200, {"content-type": "application/json; charset=utf-8"},
                          json.dumps(payload), api.ADD_URL)


def client_with(responses: list[_http.Response]) -> api.Api:
    client = api.Api()
    client.session = FakeSession(responses)  # type: ignore[assignment]
    return client


def test_logged_in_add_reads_current_quantity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    state = made(Items={"111111": {"CartQuantity": "1.00"}})
    success = made(UpdateCart=True, Result=2, CartAction=1,
                   Items=[{"ProductSKU": "111111", "Quantity": 3, "IsValid": True}])
    client = client_with([state, success])
    data = client.add("111111", 2, address=ADDRESS)
    assert data["UpdateCart"] is True
    calls = client.session.calls  # type: ignore[attr-defined]
    assert calls[0][0] == "POST" and calls[0][1] == api.CART_CONTEXT_URL
    method, url, form, _ = calls[1]
    assert method == "POST" and url == api.ADD_URL
    assert form == {
        "Action": "Update",
        "CartItems[0][ProductSKU]": "111111",
        "CartItems[0][Quantity]": "3",
    }


def test_guest_wizard_walks_login_address_slot_then_add(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    client = client_with([
        made(Items={}),                                      # current cart quantity
        html('<form id="Login"></form>'),                    # add -> login modal
        html('<form id="Login"></form>'),                    # continue as guest
        html('<form class="zipCode"><input data-role-addressform="ZipCode" /></form>'),  # GET -> address
        html('<form class="zipCode"></form>'),               # POST address
        html(SLOT_HTML),                                      # GET -> slots
        html(SLOT_HTML),                                      # POST slot
        made(Success=True),                                   # GET -> pending
        made(UpdateCart=True, Result=2, CartAction=1,
             Items=[{"ProductSKU": "111111", "Quantity": 1, "IsValid": True}]),
    ])

    data = client.add("111111", 1, address=ADDRESS)
    assert data["UpdateCart"] is True
    calls = client.session.calls  # type: ignore[attr-defined]
    assert calls[1][2]["Action"] == "Update"
    assert calls[2][2] == {"selectedAction": "ContinueAsGuest"}
    address_form = calls[4][2]
    assert address_form["ZipCode"] == "10000"
    assert address_form["Latitude"] == "37,9755972"
    assert address_form["Longitude"] == "23,7335539"
    slot_form = calls[6][2]
    assert slot_form["TimeSlotDate"] == "2026-11-28 07:00:00"      # disabled slot skipped
    assert slot_form["TimeSlotDateTo"] == "2026-11-28 09:00:00"
    assert slot_form["RequiresNotification"] == "True"
    assert store.get_delivery()["start"] == "2026-11-28 07:00:00"


ORDER_TABLE_ONE = """
<table class="table-order">
  <tbody><tr>
    <td><div class="table-order__title">Κωδικός Παραγγελίας</div>
        <a href="/account/istoriko-paraggelion/?OrderNumber=AAAAAAAAAAAA">AAAAAAAAAAAA</a></td>
    <td><div class="date-time">26/11/2026</div></td>
    <td><address>TEST</address></td>
    <td><div class="table-order__price price">10,00 €</div></td>
    <td><span>Ολοκληρώθηκε</span></td>
    <td><span>repeat</span></td>
  </tr></tbody>
</table>
"""

ORDER_TABLE_TWO = """
<table class="table-order">
  <tbody><tr>
    <td><div class="table-order__title">Κωδικός Παραγγελίας</div>
        <a href="/account/istoriko-paraggelion/?OrderNumber=BBBBBBBBBBBB">BBBBBBBBBBBB</a></td>
    <td><div class="date-time">20/11/2026</div></td>
    <td><address>TEST</address></td>
    <td><div class="table-order__price price">5,00 €</div></td>
    <td><span>Ολοκληρώθηκε</span></td>
    <td><span>repeat</span></td>
  </tr></tbody>
</table>
"""

ORDER_DETAIL = """
<div class="order-header">
  <div class="order-header__left"><div class="date-time">26/11/2026</div></div>
  <div class="order-header__center"><div class="order-number">AAAAAAAAAAAA</div>
    <div class="status">Ολοκληρώθηκε</div></div>
  <div class="order-header__right"><div class="price">10,00 €</div></div>
</div>
<section class="cart history"><table><tbody>
  <tr class="product horizontal-products__tr">
    <td class="product-td"><h4 class="horizontal-products__title">
      <a href="/p/test-111111/">TEST ONE</a></h4></td>
    <td class="quant-td"><div class="quantTxt">1 τεμ.</div></td>
    <td class="priceWrp"><div class="price">1,89 €</div></td>
  </tr>
</tbody></table></section>
"""


def test_orders_paginates(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    first = _http.Response(200, {"content-type": "text/html"}, ORDER_TABLE_ONE, api.ORDERS_URL)
    second = _http.Response(200, {"content-type": "text/html"}, ORDER_TABLE_TWO,
                            api.ORDERS_URL + "?pg=2")
    client = client_with([first, second])
    data = client.orders(limit=2)
    assert [o["number"] for o in data["orders"]] == ["AAAAAAAAAAAA", "BBBBBBBBBBBB"]
    assert client.session.calls[0][1] == api.ORDERS_URL  # type: ignore[attr-defined]
    assert "pg=2" in client.session.calls[1][1]  # type: ignore[attr-defined]


def test_order_detail_fetches_by_number(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    detail = _http.Response(200, {"content-type": "text/html"}, ORDER_DETAIL,
                            api.ORDERS_URL + "?OrderNumber=AAAAAAAAAAAA")
    client = client_with([detail])
    data = client.order("AAAAAAAAAAAA")
    assert data["order"]["number"] == "AAAAAAAAAAAA"
    assert data["order"]["items"][0]["name"] == "TEST ONE"
    assert data["order"]["items"][0]["line_total"] == 1.89
    assert data["order"]["items"][0]["unit_price"] == 1.89
    assert "OrderNumber=AAAAAAAAAAAA" in client.session.calls[0][1]  # type: ignore[attr-defined]


def test_orders_requires_login(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    redirect = _http.Response(200, {"content-type": "text/html"}, "<html>login</html>",
                              "https://www.sklavenitis.gr/account/signin-register/")
    client = client_with([redirect])
    with pytest.raises(api.AuthError):
        client.orders()


def test_login_posts_the_site_form(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    login_html = '<form id="Login"><input name="__RequestVerificationToken" type="hidden" value="tok" /></form>'
    account = _http.Response(200, {"content-type": "text/html"},
                             "<html>account</html>", "https://www.sklavenitis.gr/account/")
    client = client_with([
        html("<html>home</html>"),
        html(login_html),
        made(Success=True),
        account,
    ])
    data = client.login("user@example.invalid", "secret")
    assert data["authenticated"] is True
    form = client.session.calls[2][2]  # type: ignore[attr-defined]
    assert form["__RequestVerificationToken"] == "tok"
    assert form["FormName"] == "Login"
    assert form["Email"] == "user@example.invalid"
    assert form["Password"] == "secret"


def test_remove_uses_zero_quantity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    client = client_with([
        made(UpdateCart=True, Result=2, CartAction=2,
             Items=[{"ProductSKU": "111111", "Quantity": 0, "IsValid": True}]),
    ])
    client.remove("111111")
    _, _, form, _ = client.session.calls[0]  # type: ignore[attr-defined]
    assert form["Action"] == "Remove"
    assert form["CartItems[0][Quantity]"] == "0"


def test_set_quantity_zero_delegates_to_remove(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    client = client_with([
        made(UpdateCart=True, Result=2, CartAction=2, Items=[]),
    ])
    client.set_quantity("111111", 0)
    assert client.session.calls[0][2]["Action"] == "Remove"  # type: ignore[attr-defined]


def test_resolve_sku() -> None:
    assert api.resolve_sku("123456") == "123456"
    assert api.resolve_sku("https://www.sklavenitis.gr/p/name-1709870/") == "1709870"
    assert api.resolve_sku("1709870/") == "1709870"
