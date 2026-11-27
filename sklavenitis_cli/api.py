"""Sklavenitis.gr endpoints and the add-to-cart state machine.

Everything here was verified against the live site. The important details:

* Cart mutations are form posts to ``AddToCartUserFlow.Index`` with bracketed
  keys: ``CartItems[0][ProductSKU]`` and ``CartItems[0][Quantity]``.
  ``Quantity`` is absolute; ``Action=Remove`` needs ``Quantity=0``.
* A guest's first add is a small wizard: login modal -> "continue as guest" ->
  address -> delivery slot -> add. Logged-in users with an address and slot
  selected get a single JSON response.
* The delivery slot must be selected before the item lands in the cart; the CLI
  defaults to the first (nearest) enabled slot.
* The site uses reCAPTCHA v3 on the login form. The CLI posts the form directly
  and accepts an optional token, but it never pretends to solve the captcha:
  cookie import is the documented fallback.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import _http, parse, store
from ._http import Response

BASE = _http.BASE

LOGIN_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/"
LOGOUT_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.Account.LogOut/"
ADD_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/"
CART_CONTEXT_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.ClientContext.Index/?type=Cart"
CART_VIEW_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.Cart.Index/?View=FullCart&filtersOn=True"
ADDRESS_SEARCH_URL = BASE + "/api/Address/Search"
ADDRESS_DETAILS_URL = BASE + "/api/Address/Details"
SLOT_CHANGE_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.TimeSlotChangeUserFlow.Index/"
SLOT_SELECT_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.TimeSlotChangeUserFlow.TimeSlotSelection/"
AUTOCOMPLETE_URL = BASE + "/gr/ajax/Atcom.Sites.Yoda.Components.Autocomplete.SearchAutocomplete/"
SEARCH_URL = BASE + "/apotelesmata-anazitisis/"
ORDERS_URL = BASE + "/account/istoriko-paraggelion/"

SORTS = {
    "relevance": "ByPopularity",
    "cheapest": "PriceAsc",
    "expensive": "PriceDesc",
    "name": "NameAsc",
    "unit": "UnitPriceAsc",
}

SKU_RE = re.compile(r"(\d{5,})(?:[/?#]|$)")
AUTH_COOKIE = ".AspNet.ApplicationCookie_Frontend4"
PAGE_SIZE = 24


class ApiError(RuntimeError):
    pass


class AuthError(ApiError):
    pass


class AddressRequired(ApiError):
    pass


def resolve_sku(target: str) -> str:
    """Accept a bare SKU, a product URL, or any string containing the SKU."""
    target = (target or "").strip()
    if target.isdigit():
        return target
    m = SKU_RE.search(target)
    if m:
        return m.group(1)
    raise ApiError(f"cannot find a Sklavenitis product id in {target!r}")


def greek_decimal(value: Any) -> str:
    """The address form posts Greek-locale decimals (comma)."""
    s = f"{float(value):.10f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


class Api:
    def __init__(self, timeout: int = 30, verbose: bool = False) -> None:
        self.session = _http.Session(timeout=timeout)
        self.session.verbose = verbose
        self.verbose = verbose
        self.config = store.load_config()

    # ------------------------------------------------------------------ headers
    @staticmethod
    def ajax(*, new: bool = False, modal: bool = False, noredirect: bool = False,
             referer: Optional[str] = None) -> dict[str, str]:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "AnalyticsTracker-Enabled": "true",
            "Origin": BASE,
        }
        if new:
            headers["X-UserFlow-New"] = "true"
        if modal:
            headers["X-Modal"] = "true"
        if noredirect:
            headers["X-NoRedirect"] = "true"
        if referer:
            headers["Referer"] = referer
        return headers

    def _referer(self) -> str:
        return BASE + "/cart/"

    # -------------------------------------------------------------------- auth
    def authenticated_hint(self) -> bool:
        return bool(self.session.cookie(AUTH_COOKIE))

    def is_logged_in(self) -> bool:
        # The account page can answer the first request with a 403 bot
        # challenge; that response sets the cookie the retry needs.
        r = self.session.get(BASE + "/account/", headers={"Referer": BASE + "/"})
        if r.status == 403:
            r = self.session.get(BASE + "/account/", headers={"Referer": BASE + "/"})
        final = (r.url or "").rstrip("/")
        if r.status != 200:
            return False
        return "/account/signin" not in final and "/account/login" not in final

    def login(self, email: str, password: str, *, remember: bool = True,
              recaptcha_token: Optional[str] = None) -> dict[str, Any]:
        if not email or not password:
            raise AuthError("email and password are required")
        # Prime the session and get the antiforgery cookie/token.
        self.session.get(BASE + "/")
        modal = self.session.get(LOGIN_URL, headers=self.ajax(referer=BASE + "/"))
        token = parse.form_token(modal.text)
        if not token:
            raise AuthError("the login form had no __RequestVerificationToken; the site may have changed")
        form = {
            "__RequestVerificationToken": token,
            "FormName": "Login",
            "Email": email,
            "Password": password,
            "RememberMe": "true" if remember else "false",
            "returnUrl": "/",
            "isHomePage": "true",
        }
        if recaptcha_token:
            form["g-recaptcha-response"] = recaptcha_token
        r = self.session.post(
            LOGIN_URL,
            form,
            headers=self.ajax(modal=True, noredirect=True, referer=BASE + "/"),
        )
        if r.is_json:
            data = r.json()
            if isinstance(data, dict) and data.get("RedirectUrl"):
                if self.is_logged_in():
                    return {"authenticated": True, "email": email, "redirect": data["RedirectUrl"]}
        if self.is_logged_in():
            return {"authenticated": True, "email": email}
        raise AuthError(
            "login failed: Sklavenitis returned the sign-in form. "
            "Check the email/password. The form is protected by reCAPTCHA v3; "
            "if the site rejects automated logins, log in in a browser and import "
            "the Cookie header with `sklavenitis auth import --cookie '...'`, or "
            "pass a fresh token with --recaptcha-token."
        )

    def logout(self) -> dict[str, Any]:
        r = self.session.post(
            LOGOUT_URL,
            {"returnUrl": "/", "isHomePage": "true"},
            headers=self.ajax(noredirect=True, referer=BASE + "/"),
        )
        data = r.json() if r.is_json else {}
        self.session.clear()
        store.clear_delivery()
        return {"ok": True, "server": data or True}

    def import_cookies(self, raw: str) -> dict[str, Any]:
        raw = raw.strip()
        if raw.lower().startswith("cookie:"):
            raw = raw.split(":", 1)[1].strip()
        cookies: list[dict[str, Any]] = []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except ValueError as exc:
                raise AuthError(f"cookie JSON is invalid: {exc}") from exc
            if not isinstance(parsed, list):
                raise AuthError("cookie JSON must be a list")
            cookies = [c for c in parsed if isinstance(c, dict) and c.get("name")]
        else:
            for part in raw.split(";"):
                if "=" not in part:
                    continue
                name, value = part.split("=", 1)
                name = name.strip()
                if not name:
                    continue
                cookies.append({
                    "name": name,
                    "value": value.strip(),
                    "domain": ".sklavenitis.gr",
                    "path": "/",
                    "secure": True,
                    "expires": None,
                })
        if not cookies:
            raise AuthError("no cookies found")

        # Validate before touching the live jar: a bad paste must not throw away
        # the guest cart (or a working login) that is already on disk.
        candidate = _http.Session(timeout=self.session.timeout)
        candidate.jar = _http.cookies_to_jar(cookies)
        candidate.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(candidate.jar))
        candidate.save_enabled = False
        original = self.session
        self.session = candidate
        try:
            authenticated = self.is_logged_in()
        except _http.TransportError as exc:
            raise AuthError(f"could not verify the imported cookies: {exc}") from exc
        finally:
            self.session = original

        if not authenticated:
            raise AuthError(
                "the imported cookies are not logged in; the existing session was preserved"
            )
        self.session.jar = candidate.jar
        self.session.opener = candidate.opener
        self.session.save()
        return {"imported": len(cookies), "authenticated": True}

    # ------------------------------------------------------------------ search
    def search(self, query: str, *, limit: int = 10, page: int = 1,
               sort: str = "relevance") -> dict[str, Any]:
        if not query.strip():
            raise ApiError("query is empty")
        sortby = SORTS.get(sort, SORTS["relevance"])
        results: list[dict[str, Any]] = []
        total = 0
        current = max(1, page)
        pages = 0
        while len(results) < limit and pages < 20:
            params = {"Query": query, "sortby": sortby, "pg": current}
            r = self.session.get(SEARCH_URL + "?" + urllib.parse.urlencode(params))
            if r.status != 200:
                raise ApiError(f"search returned HTTP {r.status}")
            parsed = parse.parse_search(r.text)
            if pages == 0:
                total = parsed.get("total") or 0
            products = parsed.get("products") or []
            if not products:
                break
            results.extend(products)
            pages += 1
            current += 1
        results = results[:limit]
        return {
            "query": query,
            "sort": sort,
            "page": page,
            "count": len(results),
            "total": total,
            "results": results,
        }

    def autocomplete(self, term: str) -> list[dict[str, Any]]:
        r = self.session.get(
            AUTOCOMPLETE_URL + "?" + urllib.parse.urlencode({"term": term}),
            headers=self.ajax(referer=BASE + "/"),
        )
        if not r.is_json:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            sku = None
            m = SKU_RE.search(str(item.get("url") or ""))
            if m:
                sku = m.group(1)
            out.append({"label": item.get("label"), "category": item.get("category"),
                        "url": item.get("url"), "sku": sku})
        return out

    # ------------------------------------------------------------------ orders
    def _orders_page(self, page: int) -> str:
        url = ORDERS_URL if page == 1 else ORDERS_URL + "?" + urllib.parse.urlencode({"pg": page})
        r = self.session.get(url, headers={"Referer": BASE + "/account/"})
        final = r.url or ""
        if (r.status != 200 or "/account/istoriko-paraggelion" not in final
                or "/account/signin" in final or "/account/login" in final):
            raise AuthError("log in to see the order history: `sklavenitis auth login`")
        return r.text

    def orders(self, limit: int = 10) -> dict[str, Any]:
        if limit < 1:
            raise ApiError("--limit must be at least 1")
        orders: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while len(orders) < limit and page <= 50:
            rows = parse.parse_orders(self._orders_page(page))
            if not rows:
                break
            fresh = 0
            for order in rows:
                number = order.get("number")
                key = str(number) if number else None
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                orders.append(order)
                fresh += 1
                if len(orders) >= limit:
                    break
            if not fresh:
                break
            page += 1
        return {
            "count": len(orders[:limit]),
            "orders": orders[:limit],
            "has_more": len(orders) >= limit,
        }

    def order(self, target: str) -> dict[str, Any]:
        target = (target or "").strip()
        if not target:
            raise ApiError("an order number or detail URL is required")
        if target.startswith("http://") or target.startswith("https://"):
            url = target
        elif "?" in target or "/" in target:
            url = urllib.parse.urljoin(ORDERS_URL, target)
        else:
            url = ORDERS_URL + "?" + urllib.parse.urlencode({"OrderNumber": target})
        r = self.session.get(url, headers={"Referer": ORDERS_URL})
        final = r.url or ""
        if (r.status != 200 or "/account/istoriko-paraggelion" not in final
                or "/account/signin" in final or "/account/login" in final):
            raise AuthError("log in to see the order history: `sklavenitis auth login`")
        order = parse.parse_order_detail(r.text)
        if not order.get("number") and not order.get("items"):
            raise ApiError(f"no order found for {target!r}")
        return {"order": order, "url": final}

    # -------------------------------------------------------------------- cart
    def cart_state(self) -> dict[str, Any]:
        r = self.session.post(CART_CONTEXT_URL, {}, headers=self.ajax(referer=self._referer()))
        if not r.is_json:
            raise ApiError(f"cart context returned HTTP {r.status}: {r.text[:160]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ApiError("cart context was not a JSON object")
        return data

    def cart_items(self) -> list[dict[str, Any]]:
        r = self.session.get(CART_VIEW_URL, headers=self.ajax(referer=self._referer()))
        if r.status != 200:
            return []
        return parse.parse_cart_items(r.text)

    def cart(self) -> dict[str, Any]:
        state = self.cart_state()
        items = self.cart_items()
        return {
            "authenticated": self.authenticated_hint(),
            "address": state.get("FullAddressInfo") or state.get("AddressInfo"),
            "slot": {
                "info": state.get("SlotInfo"),
                "day": state.get("SlotDay"),
                "with_day": state.get("SlotInfoWithDay"),
                "date": state.get("SlotDate"),
                "hub": state.get("Hub"),
            },
            "summary": {
                "items": state.get("SummaryText"),
                "total": state.get("GrandTotal"),
                "can_checkout": state.get("CanProceedToCheckout"),
                "minimum_order_reached": state.get("MinimumOrderAmountReached"),
            },
            "items": items,
        }

    # ----------------------------------------------------- add-to-cart wizard
    def _address_form(self, address: dict[str, Any]) -> dict[str, str]:
        return {
            "ZipCode": str(address["zip"]),
            "Street": str(address.get("street") or ""),
            "State": str(address.get("state") or ""),
            "Number": str(address.get("number") or ""),
            "Location": str(address.get("location") or ""),
            "PromptAdditionalNotes": "false",
            "Latitude": greek_decimal(address["latitude"]),
            "Longitude": greek_decimal(address["longitude"]),
            "Address": str(address.get("label") or address.get("location") or address["zip"]),
        }

    def _cart_post(self, form: dict[str, Any], *, new: bool = False,
                   modal: bool = False, noredirect: bool = False) -> Response:
        return self.session.post(
            ADD_URL,
            form,
            headers=self.ajax(new=new, modal=modal, noredirect=noredirect,
                              referer=self._referer()),
        )

    def _cart_get(self) -> Response:
        return self.session.get(ADD_URL, headers=self.ajax(referer=self._referer()))

    @staticmethod
    def _qty(value: float) -> str:
        return f"{float(value):g}"

    @staticmethod
    def _cart_result(data: Any) -> dict[str, Any]:
        if parse.is_cart_result(data):
            result = data.get("Result")
            if result is not None and result != 2:
                raise ApiError(f"the site rejected the cart change: {data}")
            return data
        raise ApiError(f"cart update failed: {data}")

    def _mutate(self, action: str, sku: str, quantity: float) -> dict[str, Any]:
        resp = self._cart_post({
            "Action": action,
            "CartItems[0][ProductSKU]": sku,
            "CartItems[0][Quantity]": self._qty(quantity),
        }, new=True)
        if resp.is_json:
            return self._cart_result(resp.json())
        if parse.is_login_form(resp.text):
            raise AuthError("this cart mutation needs a logged-in session; run `sklavenitis auth login`")
        raise ApiError(f"cart update returned HTTP {resp.status}: {resp.text[:160]}")

    def set_quantity(self, sku: str, quantity: float) -> dict[str, Any]:
        if quantity <= 0:
            return self.remove(sku)
        return self._mutate("Update", sku, quantity)

    def remove(self, sku: str) -> dict[str, Any]:
        return self._mutate("Remove", sku, 0)

    def clear_cart(self) -> dict[str, Any]:
        removed = []
        for item in self.cart_items():
            self.remove(str(item["sku"]))
            removed.append(str(item["sku"]))
        return {"removed": removed, "count": len(removed)}

    def add(self, sku: str, quantity: float = 1, *,
            address: Optional[dict[str, Any]] = None,
            slot_index: int = 0) -> dict[str, Any]:
        """Add one SKU, walking the guest wizard when the site asks for it.

        ``slot_index`` is zero-based into the enabled slots, which are in
        chronological order; 0 is the nearest delivery date.
        """
        if quantity <= 0:
            raise ApiError("quantity must be greater than zero")
        address = address or store.get_address(self.config)
        # `cart add` is additive. The site's own quantity box posts the new
        # absolute quantity, so read the current line first.
        state = self.cart_state()
        entry = (state.get("Items") or {}).get(str(sku)) or {}
        try:
            current = float(entry.get("CartQuantity") or 0)
        except (TypeError, ValueError):
            current = 0.0
        target = current + quantity
        resp = self._cart_post({
            "Action": "Update",
            "CartItems[0][ProductSKU]": sku,
            "CartItems[0][Quantity]": self._qty(target),
        }, new=True)

        guest_done = False
        address_done = False
        slot_done = False
        chosen_slot: Optional[dict[str, Any]] = None
        for _ in range(16):
            if resp.is_json:
                data = resp.json()
                if parse.is_cart_result(data):
                    if chosen_slot:
                        self.config = store.set_delivery(chosen_slot)
                    else:
                        self.config = store.load_config()
                    return self._cart_result(data)
                if isinstance(data, dict) and data.get("Success"):
                    resp = self._cart_get()
                    continue
                raise ApiError(f"add-to-cart failed: {data}")

            page = resp.text
            if parse.is_login_form(page):
                if guest_done:
                    raise AuthError(
                        "the site wants a login before adding to the cart; "
                        "run `sklavenitis auth login` or log in in a browser and import the cookie"
                    )
                guest_done = True
                self._cart_post({"selectedAction": "ContinueAsGuest"},
                                modal=True, noredirect=True)
                resp = self._cart_get()
                continue

            if parse.is_address_form(page):
                if address_done:
                    raise ApiError("the delivery address was rejected; set a served address with `sklavenitis address set`")
                if not address:
                    raise AddressRequired(
                        "a delivery address is required before the first add; "
                        "run `sklavenitis address set '<street, city or postal code>'`"
                    )
                address_done = True
                self._cart_post(self._address_form(address), noredirect=True)
                resp = self._cart_get()
                continue

            if parse.is_slot_form(page):
                if slot_done:
                    raise ApiError("the delivery slot was rejected; retry with `sklavenitis delivery set <n>`")
                slots = parse.parse_slots(page)
                if not slots:
                    raise ApiError("the site returned no available delivery slots for this address")
                slot_index = max(slot_index, 0)
                if slot_index >= len(slots):
                    raise ApiError(
                        f"delivery slot {slot_index + 1} is out of range; "
                        f"{len(slots)} slots are available (run `sklavenitis delivery`)"
                    )
                chosen = slots[slot_index]
                chosen_slot = chosen
                fields = parse.slot_form_fields(page)
                form = {
                    "TimeSlotDate": chosen["start"],
                    "TimeSlotDateTo": chosen["end"],
                    **fields,
                }
                slot_done = True
                self._cart_post(form, noredirect=True)
                resp = self._cart_get()
                continue

            raise ApiError(f"unexpected add-to-cart response (HTTP {resp.status}): {page[:160]}")

        raise ApiError("add-to-cart did not finish after 16 steps")

    # ----------------------------------------------------------------- address
    def address_search(self, term: str) -> list[dict[str, Any]]:
        if len(term.strip()) < 3:
            raise ApiError("address search needs at least 3 characters")
        r = self.session.get(
            ADDRESS_SEARCH_URL + "?" + urllib.parse.urlencode({"term": term}),
            headers=self.ajax(referer=BASE + "/"),
        )
        if not r.is_json:
            raise ApiError(f"address search returned HTTP {r.status}")
        data = r.json()
        if not isinstance(data, dict) or not data.get("Success"):
            errors = (data or {}).get("Errors") if isinstance(data, dict) else None
            message = ""
            if errors:
                message = "; ".join(str(e.get("Message") if isinstance(e, dict) else e) for e in errors)
            raise ApiError(message or "address search failed")
        return list(data.get("Response") or [])

    def address_details(self, place_id: str, description: str) -> dict[str, Any]:
        r = self.session.get(
            ADDRESS_DETAILS_URL + "?" + urllib.parse.urlencode({"id": place_id, "text": description}),
            headers=self.ajax(referer=BASE + "/"),
        )
        if not r.is_json:
            raise ApiError(f"address details returned HTTP {r.status}")
        data = r.json()
        if not isinstance(data, dict) or not data.get("Success"):
            raise ApiError("address details failed")
        return data.get("Response") or {}

    def set_address(self, query: str, *, pick: int = 1) -> dict[str, Any]:
        candidates = self.address_search(query)
        if not candidates:
            raise ApiError(f"no address matches {query!r}")
        if pick < 1 or pick > len(candidates):
            raise ApiError(f"pick must be between 1 and {len(candidates)}")
        candidate = candidates[pick - 1]
        details = self.address_details(str(candidate["ID"]), str(candidate["Description"]))
        if not details.get("ZipCodeServed"):
            raise ApiError(f"Sklavenitis does not deliver to {candidate['Description']}")
        raw = details.get("Address") or {}
        if not raw.get("ZipCode"):
            raise ApiError("the address lookup returned no postal code")
        address = {
            "label": raw.get("AutocompleteFormattedAddress") or candidate["Description"],
            "street": raw.get("Street") or "",
            "number": raw.get("Number") or "",
            "location": raw.get("Location") or "",
            "state": raw.get("State") or "",
            "country": raw.get("Country") or "Ελλάδα",
            "zip": str(raw.get("ZipCode")),
            "latitude": raw.get("Latitude"),
            "longitude": raw.get("Longitude"),
            "place_id": candidate["ID"],
        }
        self.config = store.set_address(address)
        # Set the server-side Zone/hub for this cookie jar too.
        zone_error = None
        try:
            self.session.post(SLOT_CHANGE_URL, self._address_form(address),
                              headers=self.ajax(noredirect=True, referer=BASE + "/"))
        except _http.TransportError as exc:  # pragma: no cover - transport path
            zone_error = str(exc)
        return {"address": address, "candidates": candidates, "zone_error": zone_error}

    # ----------------------------------------------------------------- delivery
    def _slot_page(self) -> tuple[str, Optional[str]]:
        r = self.session.get(SLOT_CHANGE_URL, headers=self.ajax(referer=self._referer()))
        if r.is_json:
            r = self.session.get(SLOT_CHANGE_URL, headers=self.ajax(referer=self._referer()))
        if parse.is_address_form(r.text):
            address = store.get_address(self.config)
            if not address:
                raise AddressRequired(
                    "set a delivery address first: `sklavenitis address set '<street, city or postal code>'`"
                )
            self.session.post(SLOT_CHANGE_URL, self._address_form(address),
                              headers=self.ajax(noredirect=True, referer=BASE + "/"))
            r = self.session.get(SLOT_CHANGE_URL, headers=self.ajax(referer=self._referer()))
            if r.is_json:
                r = self.session.get(SLOT_CHANGE_URL, headers=self.ajax(referer=self._referer()))
        return r.text, parse.form_token(r.text)

    def delivery(self) -> dict[str, Any]:
        page, _token = self._slot_page()
        slots = parse.parse_slots(page)
        state = self.cart_state()
        current = {
            "info": state.get("SlotInfo"),
            "day": state.get("SlotDay"),
            "with_day": state.get("SlotInfoWithDay"),
            "date": state.get("SlotDate"),
            "hub": state.get("Hub"),
        }
        saved = store.get_delivery(self.config)
        return {
            "current": current,
            "saved": saved,
            "address": state.get("FullAddressInfo") or state.get("AddressInfo"),
            "nearest": slots[0] if slots else None,
            "slots": slots,
        }

    def set_delivery(self, *, index: Optional[int] = None,
                     start: Optional[str] = None) -> dict[str, Any]:
        page, token = self._slot_page()
        slots = parse.parse_slots(page)
        if not slots:
            raise ApiError("no available delivery slots for this address")
        chosen = None
        if start:
            for slot in slots:
                if start in (slot.get("start"), slot.get("display"), slot.get("timespan")):
                    chosen = slot
                    break
            if chosen is None:
                raise ApiError(f"no slot matching {start!r}")
        else:
            i = (index or 1) - 1
            if i < 0 or i >= len(slots):
                raise ApiError(f"slot number must be between 1 and {len(slots)}")
            chosen = slots[i]
        form = {
            "TimeSlotDate": chosen["start"],
            "TimeSlotDateTo": chosen["end"],
            "RequiresNotification": "False",
            "Notification": "",
        }
        if token:
            form["__RequestVerificationToken"] = token
            self.session.post(SLOT_SELECT_URL, form,
                              headers=self.ajax(noredirect=True, referer=self._referer()))
        self.session.post(SLOT_CHANGE_URL, form,
                          headers=self.ajax(noredirect=True, referer=self._referer()))
        self.config = store.set_delivery(chosen)
        return {"selected": chosen, "slots": slots}
