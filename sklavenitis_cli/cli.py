"""Command line interface: `sklavenitis search`, `sklavenitis cart`, ...

Human output by default, ``--json`` for assistants and scripts. The cart is the
site's real cart in the cookie jar — guest or logged in.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any, Optional

from . import __version__
from . import api as api_mod
from . import store
from ._http import TransportError
from .api import Api, ApiError, AddressRequired, AuthError, SORTS

EMAIL_ENV = "SKLAVENITIS_EMAIL"
PASSWORD_ENV = "SKLAVENITIS_PASSWORD"
RECAPTCHA_ENV = "SKLAVENITIS_RECAPTCHA_TOKEN"


class UsageError(RuntimeError):
    pass


def money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    s = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{s} €"


def build_api(args: argparse.Namespace) -> Api:
    return Api(timeout=args.timeout, verbose=getattr(args, "verbose", False))


def emit(data: Any, args: argparse.Namespace) -> None:
    if not args.json:
        return
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


def line_quantity(result: Any, fallback: Optional[float]) -> Optional[float]:
    """The final line quantity from the site's mutation response."""
    if isinstance(result, dict):
        items = result.get("Items") or []
        if items and isinstance(items[0], dict):
            value = items[0].get("Quantity")
            if isinstance(value, (int, float)):
                return float(value)
    return fallback


def cart_common(cart: dict[str, Any]) -> None:
    who = "account" if cart.get("authenticated") else "guest"
    items = cart.get("items") or []
    total = (cart.get("summary") or {}).get("total") or "—"
    address = cart.get("address") or "no address"
    slot = ((cart.get("slot") or {}).get("with_day")
            or (cart.get("slot") or {}).get("info") or "no delivery slot")
    print(f"{len(items)} item(s) · {total} · {who}")
    print(f"  delivery: {slot} · {address}")
    for item in items:
        qty = item.get("quantity")
        qty_txt = f"{qty:g}" if isinstance(qty, (int, float)) else "?"
        print(f"  {qty_txt:>4} × {money(item.get('unit_price')):>10}  {item.get('name') or ''}")
        print(f"       sku {item.get('sku')}")


# --------------------------------------------------------------------------- search

def cmd_search(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise UsageError("--limit must be at least 1")
    client = build_api(args)
    data = client.search(args.query, limit=args.limit, page=args.page, sort=args.sort)
    if args.json:
        emit(data, args)
        return 0 if data["results"] else 1
    results = data["results"]
    if not results:
        print(f"no results for {args.query!r}", file=sys.stderr)
        return 1
    print(f"{len(results)} of {data.get('total') or len(results)} results for {args.query!r} ({args.sort})")
    for i, item in enumerate(results, 1):
        price = money(item.get("price"))
        print(f"{i:>2}. {price:>12}  {item.get('name')}")
        print(f"    sku {item.get('sku')} · step {item.get('step') or 1} · "
              f"available {item.get('available') if item.get('available') is not None else '?'}")
        if item.get("url"):
            print(f"    {item['url']}")
    return 0


# --------------------------------------------------------------------------- orders

def cmd_orders(args: argparse.Namespace) -> int:
    data = build_api(args).orders(limit=args.limit)
    if args.json:
        emit(data, args)
        return 0
    orders = data.get("orders") or []
    if not orders:
        print("no orders found")
        return 0
    print(f"{len(orders)} order(s)")
    for order in orders:
        line = "  ".join(
            str(value) for value in (
                order.get("number") or "?",
                order.get("date") or "?",
                order.get("total") or "?",
                order.get("status") or "",
            ) if value
        )
        print(f"  {line}")
        items = order.get("items") or []
        if items:
            print(f"    {', '.join(items[:4])}{' …' if len(items) > 4 else ''}")
    return 0


def cmd_order(args: argparse.Namespace) -> int:
    data = build_api(args).order(args.target)
    if args.json:
        emit(data, args)
        return 0
    order = data.get("order") or {}
    print(" · ".join(str(value) for value in (
        order.get("number") or "?",
        order.get("date") or "?",
        order.get("total") or "?",
        order.get("status") or "",
    ) if value))
    for item in order.get("items") or []:
        quantity = item.get("quantity")
        quantity_txt = f"{quantity:g}" if isinstance(quantity, (int, float)) else "?"
        unit = (money(item.get("unit_price")) if item.get("unit_price") is not None
                else (item.get("price") or "—"))
        line = (money(item.get("line_total")) if item.get("line_total") is not None
                else (item.get("price") or "—"))
        print(f"  {quantity_txt:>4} × {unit:>10} = {line:>10}  {item.get('name') or ''}")
        if item.get("sku"):
            print(f"       sku {item['sku']}")
    return 0


# ----------------------------------------------------------------------------- cart

def cmd_cart(args: argparse.Namespace) -> int:
    action = args.cart_command or "show"
    client = build_api(args)

    if action == "show":
        data = client.cart()
        if args.json:
            emit(data, args)
        else:
            cart_common(data)
        return 0

    if action == "add":
        sku = api_mod.resolve_sku(args.target)
        address = store.get_address()
        if not address and not client.authenticated_hint():
            raise AddressRequired(
                "a delivery address is required before the first add; "
                "run `sklavenitis address set '<street, city or postal code>'`"
            )
        result = client.add(sku, args.quantity, address=address, slot_index=max(0, args.slot - 1))
        cart = client.cart()
        final = line_quantity(result, args.quantity)
        out = {"ok": True, "action": "add", "sku": sku, "quantity": final,
               "added_quantity": args.quantity, "result": result, "cart": cart}
        if args.json:
            emit(out, args)
        else:
            print(f"added {args.quantity:g}; sku {sku} is now at {final:g} "
                  f"(nearest delivery slot)")
            cart_common(cart)
        return 0

    if action == "remove":
        sku = api_mod.resolve_sku(args.target)
        result = client.remove(sku)
        cart = client.cart()
        if args.json:
            emit({"ok": True, "action": "remove", "sku": sku, "quantity": 0,
                  "result": result, "cart": cart}, args)
        else:
            print(f"removed sku {sku}")
            cart_common(cart)
        return 0

    if action == "set":
        if args.quantity <= 0:
            raise UsageError("quantity must be greater than zero; use `cart remove` instead")
        sku = api_mod.resolve_sku(args.target)
        result = client.set_quantity(sku, args.quantity)
        cart = client.cart()
        final = line_quantity(result, args.quantity)
        if args.json:
            emit({"ok": True, "action": "set", "sku": sku, "quantity": final,
                  "result": result, "cart": cart}, args)
        else:
            print(f"set sku {sku} to {final:g}")
            cart_common(cart)
        return 0

    if action == "clear":
        result = client.clear_cart()
        cart = client.cart()
        if args.json:
            emit({"ok": True, "action": "clear", "sku": None, "quantity": None,
                  "result": result, "cart": cart}, args)
        else:
            print(f"removed {result['count']} item(s)")
            cart_common(cart)
        return 0

    raise UsageError(f"unknown cart command {action!r}")


# ------------------------------------------------------------------------ address

def cmd_address(args: argparse.Namespace) -> int:
    action = args.address_command or "show"
    if action == "set":
        client = build_api(args)
        data = client.set_address(args.query, pick=args.pick)
        if args.json:
            emit(data, args)
        else:
            address = data["address"]
            print(f"address: {address['label']}")
            print(f"  postal code {address['zip']} · {address.get('location')}")
        return 0
    if action == "show":
        address = store.get_address()
        if args.json:
            emit({"address": address}, args)
        else:
            if not address:
                print("no address configured")
                return 0
            print(address.get("label"))
            print(f"  postal code {address.get('zip')} · {address.get('location')}")
        return 0
    if action == "clear":
        store.clear_address()
        if args.json:
            emit({"address": None}, args)
        else:
            print("address cleared")
        return 0
    raise UsageError(f"unknown address command {action!r}")


# ----------------------------------------------------------------------- delivery

def cmd_delivery(args: argparse.Namespace) -> int:
    action = args.delivery_command or "list"
    client = build_api(args)
    if action == "list":
        data = client.delivery()
        if args.json:
            emit(data, args)
            return 0
        current = data.get("current") or {}
        print(f"current: {current.get('with_day') or current.get('info') or 'none'}"
              f" · hub {current.get('hub') or '?'}")
        print(f"address: {data.get('address') or 'none'}")
        slots = data.get("slots") or []
        if not slots:
            print("no delivery slots available")
            return 0
        for i, slot in enumerate(slots, 1):
            nearest = "  ← nearest" if i == 1 else ""
            print(f"{i:>2}. {slot.get('display') or slot.get('timespan')}{nearest}")
        return 0
    if action == "set":
        slot = args.slot
        if slot is None:
            data = client.set_delivery(index=1)
        elif slot.isdigit():
            data = client.set_delivery(index=int(slot))
        else:
            data = client.set_delivery(start=slot)
        if args.json:
            emit(data, args)
        else:
            chosen = data["selected"]
            print(f"delivery set: {chosen.get('display') or chosen.get('timespan')}")
        return 0
    raise UsageError(f"unknown delivery command {action!r}")


# ---------------------------------------------------------------------------- auth

def _credential(args: argparse.Namespace, value: Optional[str], env: str,
                prompt: str) -> str:
    if value:
        return value
    value = os.environ.get(env)
    if value:
        return value
    if sys.stdin.isatty():
        return getpass.getpass(prompt) if "password" in prompt.lower() else input(prompt)
    raise UsageError(f"set ${env} or pass the matching flag (stdin is not a terminal)")


def cmd_auth(args: argparse.Namespace) -> int:
    action = args.auth_command
    client = build_api(args)

    if action == "login":
        email = _credential(args, args.email, EMAIL_ENV, "Sklavenitis email: ")
        password = _credential(args, args.password, PASSWORD_ENV, "Sklavenitis password: ")
        token = args.recaptcha_token or os.environ.get(RECAPTCHA_ENV)
        data = client.login(email, password, remember=args.remember, recaptcha_token=token)
        if args.json:
            emit(data, args)
        else:
            print(f"logged in to Sklavenitis as {email}")
            print(f"  cookies: {store.cookie_path()}")
        return 0

    if action == "status":
        authenticated = client.is_logged_in()
        data = {
            "authenticated": authenticated,
            "cookies": str(store.cookie_path()),
            "config": str(store.config_path()),
            "address": store.get_address(),
        }
        if args.json:
            emit(data, args)
        else:
            print("logged in" if authenticated else "not logged in (guest session)")
            print(f"  cookies: {data['cookies']}")
            print(f"  address: {(data['address'] or {}).get('label') or 'not configured'}")
        return 0

    if action == "logout":
        data = client.logout()
        if args.json:
            emit(data, args)
        else:
            print("logged out; local cookies cleared")
        return 0

    if action == "import":
        raw = args.cookie
        if not raw and args.cookie_file:
            try:
                raw = open(args.cookie_file, encoding="utf-8").read()
            except OSError as exc:
                raise UsageError(f"cannot read {args.cookie_file}: {exc}") from exc
        if not raw:
            raise UsageError("pass --cookie '<Cookie header>' or --cookie-file <path>")
        data = client.import_cookies(raw)
        if args.json:
            emit(data, args)
        else:
            print(f"imported {data['imported']} cookie(s); "
                  f"{'logged in' if data['authenticated'] else 'still a guest'}")
        return 0

    raise UsageError(f"unknown auth command {action!r}")


# ----------------------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="sklavenitis",
        description="Sklavenitis.gr search and cart from the terminal: search, "
                    "delivery slots, and your real cart (guest or logged in).",
    )
    p.add_argument("--version", action="version", version=f"sklavenitis-cli {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--timeout", type=int, default=30, help="per-request timeout in seconds")
    common.add_argument("--json", action="store_true", help="machine readable output")
    common.add_argument("-v", "--verbose", action="store_true", help="extra logging on stderr")

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", parents=[common], help="search products")
    s.add_argument("query")
    s.add_argument("-n", "--limit", type=int, default=10, help="max results (default: 10)")
    s.add_argument("-p", "--page", type=int, default=1, help="first results page (default: 1)")
    s.add_argument("-s", "--sort", default="relevance", choices=sorted(SORTS))
    s.set_defaults(func=cmd_search)

    o = sub.add_parser("orders", parents=[common], help="order history (requires login)")
    o.add_argument("-n", "--limit", type=int, default=10, help="orders to show (default: 10)")
    o.set_defaults(func=cmd_orders)

    od = sub.add_parser("order", parents=[common], help="one order with its products")
    od.add_argument("target", help="order number or detail URL")
    od.set_defaults(func=cmd_order)

    c = sub.add_parser("cart", parents=[common], help="show or change the cart (default: show)")
    cart_sub = c.add_subparsers(dest="cart_command")
    cs = cart_sub.add_parser("show", parents=[common], help="items, totals, address, slot")
    cs.set_defaults(func=cmd_cart)
    ca = cart_sub.add_parser("add", parents=[common], help="add a SKU or product URL")
    ca.add_argument("target", help="SKU or product URL")
    ca.add_argument("-q", "--quantity", type=float, default=1)
    ca.add_argument("--slot", type=int, default=1,
                    help="delivery slot number from `sklavenitis delivery` (default: 1, nearest)")
    ca.set_defaults(func=cmd_cart)
    cr = cart_sub.add_parser("remove", parents=[common], help="remove a SKU from the cart")
    cr.add_argument("target", help="SKU or product URL")
    cr.set_defaults(func=cmd_cart)
    ct = cart_sub.add_parser("set", parents=[common], help="set a line's absolute quantity")
    ct.add_argument("target", help="SKU or product URL")
    ct.add_argument("-q", "--quantity", type=float, required=True)
    ct.set_defaults(func=cmd_cart)
    cc = cart_sub.add_parser("clear", parents=[common], help="remove every line")
    cc.set_defaults(func=cmd_cart)
    c.set_defaults(func=cmd_cart, cart_command=None)

    a = sub.add_parser("address", parents=[common],
                       help="the delivery address used for guest checkout")
    address_sub = a.add_subparsers(dest="address_command")
    aset = address_sub.add_parser("set", parents=[common], help="look up and store an address")
    aset.add_argument("query", help="street and number, city, or postal code")
    aset.add_argument("--pick", type=int, default=1,
                      help="candidate number when the lookup returns several (default: 1)")
    aset.set_defaults(func=cmd_address)
    ashow = address_sub.add_parser("show", parents=[common], help="show the stored address")
    ashow.set_defaults(func=cmd_address)
    aclear = address_sub.add_parser("clear", parents=[common], help="forget the stored address")
    aclear.set_defaults(func=cmd_address)
    a.set_defaults(func=cmd_address, address_command=None)

    d = sub.add_parser("delivery", parents=[common],
                       help="available delivery dates and the selected one")
    delivery_sub = d.add_subparsers(dest="delivery_command")
    dlist = delivery_sub.add_parser("list", parents=[common], help="current and available slots")
    dlist.set_defaults(func=cmd_delivery)
    dset = delivery_sub.add_parser("set", parents=[common],
                                   help="select a slot number, ISO start, or display text")
    dset.add_argument("slot", nargs="?", default=None,
                      help="1-based slot number, ISO start time, or display text (default: nearest)")
    dset.set_defaults(func=cmd_delivery)
    d.set_defaults(func=cmd_delivery, delivery_command=None)

    au = sub.add_parser("auth", parents=[common], help="log in, log out, or import a browser session")
    auth_sub = au.add_subparsers(dest="auth_command", required=True)
    al = auth_sub.add_parser("login", parents=[common], help="log in with email and password")
    al.add_argument("--email", default=None, help=f"or ${EMAIL_ENV}")
    al.add_argument("--password", default=None, help=f"or ${PASSWORD_ENV}")
    al.add_argument("--recaptcha-token", default=None,
                    help=f"reCAPTCHA v3 token if the site demands one (or ${RECAPTCHA_ENV})")
    al.add_argument("--no-remember", dest="remember", action="store_false",
                    help="do not ask the site to remember the login")
    al.set_defaults(func=cmd_auth, remember=True)
    ast = auth_sub.add_parser("status", parents=[common], help="show whether the session is logged in")
    ast.set_defaults(func=cmd_auth)
    alo = auth_sub.add_parser("logout", parents=[common], help="log out and clear local cookies")
    alo.set_defaults(func=cmd_auth)
    ai = auth_sub.add_parser("import", parents=[common],
                             help="import a Cookie header from a logged-in browser")
    ai.add_argument("--cookie", default=None, help="the Cookie request header, quoted")
    ai.add_argument("--cookie-file", default=None, help="file containing the Cookie header")
    ai.set_defaults(func=cmd_auth)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (UsageError, ApiError, AddressRequired, AuthError, TransportError,
            store.StoreError) as exc:
        if getattr(args, "json", False):
            json.dump({"error": str(exc)}, sys.stderr, ensure_ascii=False)
            print(file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
