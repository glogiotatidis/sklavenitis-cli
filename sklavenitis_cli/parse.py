"""HTML fragments from Sklavenitis, turned into small dictionaries.

The site is server-rendered ASP.NET. There is no JSON search endpoint, so the
search results and cart lines are read from the HTML. The markup is stable but
not semantic: keep every selector in this file, so a redesign touches one
module.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from typing import Any, Optional

TAG_ATTR = re.compile(r"""([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.S)
# The outer product container: the class value has a standalone ``product``
# token. Nested containers are ``product-options``, ``product-flags``, etc.
PRODUCT_TAG = re.compile(
    r"""<div\b[^>]*\bclass\s*=\s*["'](?:[^"']*\s)?product(?:\s[^"']*)?["'][^>]*>""",
    re.S | re.I,
)
SLOT_TAG = re.compile(
    r"""<div\b[^>]*\bclass\s*=\s*["'][^"']*\bdate__hour\b[^"']*["'][^>]*>""",
    re.S | re.I,
)
ORDER_HEADER = re.compile(
    r"""<[a-z0-9]+\b[^>]*\bclass\s*=\s*["'][^"']*\border-header\b[^"']*["'][^>]*>""",
    re.S | re.I,
)
ORDER_SECTION = re.compile(
    r"""<[a-z0-9]+\b[^>]*\bclass\s*=\s*["'][^"']*\border-list\b[^"']*["'][^>]*>""",
    re.S | re.I,
)
ORDER_OPTIONS = re.compile(
    r"""\bdata-plugin-orderhistory\s*=\s*(["'])(.*?)\1""",
    re.S | re.I,
)
ORDER_TABLE = re.compile(
    r"""<table\b[^>]*\bclass\s*=\s*["'][^"']*\btable-order\b[^"']*["'][^>]*>(.*?)</table>""",
    re.S | re.I,
)
ORDER_TR = re.compile(r"""<tr\b[^>]*>(.*?)</tr>""", re.S | re.I)
ORDER_TD = re.compile(r"""<td\b[^>]*>(.*?)</td>""", re.S | re.I)
ORDER_ITEM_ROW = re.compile(
    r"""<tr\b[^>]*\bclass\s*=\s*["'][^"']*\bproduct\b[^"']*["'][^>]*>(.*?)</tr>""",
    re.S | re.I,
)
ORDER_NUMBER = re.compile(
    r"""(?:Αρ\.?\s*Παραγγελίας|Αριθμός\s*Παραγγελίας|Order\s*(?:Number|No\.?))
        \s*[:#]?\s*([A-Z0-9][A-Z0-9-]{5,})""",
    re.I | re.X,
)
ORDER_NUMBER_QS = re.compile(r"OrderNumber=([A-Za-z0-9-]{4,})", re.I)
ORDER_DATE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{4}(?:[,\s]+\d{1,2}:\d{2})?"
    r"|\d{1,2}\s+[Α-Ωα-ω]+\s+\d{4})\b"
)
ORDER_TOTAL = re.compile(
    r"(?:Σύνολο(?:\s*Παραγγελίας)?|Total)[^0-9]{0,40}(\d+[.,]\d{2})\s*€",
    re.I,
)
KNOWN_STATUSES = re.compile(
    r"(Ολοκληρώθηκε|Παραδόθηκε|Σε εξέλιξη|Υπό επεξεργασία|Ακυρώθηκε|Απέσταλται)",
    re.I,
)
TOKEN_INPUT = re.compile(
    r"""<input\b[^>]*\bname\s*=\s*["']__RequestVerificationToken["'][^>]*>""",
    re.S | re.I,
)
HIDDEN_INPUT = re.compile(r"""<input\b[^>]*>""", re.S | re.I)


def attr(tag: str, name: str) -> Optional[str]:
    """Read one HTML attribute, single- or double-quoted, entities decoded."""
    for m in TAG_ATTR.finditer(tag):
        if m.group(1).lower() == name.lower():
            value = m.group(2) if m.group(2) is not None else m.group(3)
            return html_mod.unescape(value)
    return None


def text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_mod.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def greek_number(value: str) -> Optional[float]:
    """Parse ``1.234,56`` and ``1,89``; tolerate currency and NBSP."""
    if value is None:
        return None
    s = html_mod.unescape(str(value))
    s = s.replace("\u00a0", " ").replace("€", " ").strip()
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def form_token(page: str) -> Optional[str]:
    for m in TOKEN_INPUT.finditer(page):
        value = attr(m.group(0), "value")
        if value:
            return value
    return None


def hidden_inputs(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in HIDDEN_INPUT.finditer(page):
        tag = m.group(0)
        if (attr(tag, "type") or "").lower() != "hidden":
            continue
        name = attr(tag, "name")
        if name:
            out[name] = attr(tag, "value") or ""
    return out


def _json_attr(tag: str, name: str) -> dict[str, Any]:
    raw = attr(tag, name)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


# ------------------------------------------------------------------ form kinds

def is_login_form(page: str) -> bool:
    return 'id="Login"' in page or "id='Login'" in page


def is_address_form(page: str) -> bool:
    return 'data-role-addressform="ZipCode"' in page or "data-role-addressform='ZipCode'" in page


def is_slot_form(page: str) -> bool:
    return "promptslotselection" in page or "date__hour" in page


def is_cart_result(data: Any) -> bool:
    return isinstance(data, dict) and "UpdateCart" in data


# --------------------------------------------------------------------- search

def _product_blocks(page: str) -> list[str]:
    starts = [m.start() for m in PRODUCT_TAG.finditer(page)]
    return [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])]


def _product_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return "https://www.sklavenitis.gr" + href


def _product_name(block: str) -> tuple[str, Optional[str]]:
    m = re.search(
        r"""<h4\b[^>]*\bclass\s*=\s*["'][^"']*product__title[^"']*["'][^>]*>\s*
            <a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
        block, re.S | re.I | re.X,
    )
    if m:
        return text(m.group(2)), _product_url(m.group(1))
    m = re.search(
        r"""<h4\b[^>]*\bclass\s*=\s*["'][^"']*product__title[^"']*["'][^>]*>(.*?)</h4>""",
        block, re.S | re.I,
    )
    return (text(m.group(1)) if m else ""), None


def parse_search(page: str) -> dict[str, Any]:
    products: list[dict[str, Any]] = []
    for block in _product_blocks(page):
        tag_end = block.find(">")
        tag = block[: tag_end + 1] if tag_end != -1 else block
        item = _json_attr(tag, "data-item")
        plugin = _json_attr(tag, "data-plugin-product")
        if not item.get("ProductSKU") and not plugin.get("sku"):
            continue
        name, url = _product_name(block)
        price = None
        m = re.search(r"""\bdata-price\s*=\s*["']([^"']+)["']""", block, re.I)
        if m:
            price = greek_number(m.group(1))
        if price is None:
            m = re.search(
                r"""<div\b[^>]*\bclass\s*=\s*["'][^"']*\bprice\b[^"']*["'][^>]*>(.*?)</div>""",
                block, re.S | re.I,
            )
            if m:
                price = greek_number(text(m.group(1)))
        stock = plugin.get("stock") or {}
        products.append({
            "sku": str(item.get("ProductSKU") or plugin.get("sku")),
            "product_id": item.get("ProductID"),
            "name": name,
            "price": price,
            "unit": plugin.get("unitDisplay"),
            "step": plugin.get("step"),
            "max_quantity": plugin.get("maximum"),
            "available": stock.get("available"),
            "not_buyable": bool(plugin.get("notBuyable")) or bool(plugin.get("notExists")),
            "url": url,
        })

    total = len(products)
    m = re.search(r"(\d+)\s*από\s*τα\s*(\d+)", page)
    if m:
        total = int(m.group(2))
    return {"count": len(products), "total": total, "products": products}


# ------------------------------------------------------------------------ cart

def _cart_quantity(block: str) -> float:
    m = re.search(
        r"""<span\b[^>]*\bclass\s*=\s*["'][^"']*\bquantityNumber\b[^"']*["'][^>]*>
            \s*([\d.,]+)""",
        block, re.S | re.I | re.X,
    )
    if m:
        return greek_number(m.group(1)) or 0.0
    return 0.0


def parse_cart_items(page: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for block in _product_blocks(page):
        tag_end = block.find(">")
        tag = block[: tag_end + 1] if tag_end != -1 else block
        item = _json_attr(tag, "data-item")
        sku = item.get("ProductSKU")
        if not sku:
            continue
        if "quantityNumber" not in block and "remove-cart-item" not in block:
            continue
        name, url = _product_name(block)
        m = re.search(r"""\bdata-price\s*=\s*["']([^"']+)["']""", block, re.I)
        unit_price = greek_number(m.group(1)) if m else None
        quantity = _cart_quantity(block)
        items.append({
            "sku": str(sku),
            "product_id": item.get("ProductID"),
            "name": name,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": round(unit_price * quantity, 2) if unit_price is not None else None,
            "url": url,
        })
    return items


# ----------------------------------------------------------------------- orders

def parse_order_options(page: str) -> dict[str, Any]:
    m = ORDER_OPTIONS.search(page)
    if not m:
        return {}
    try:
        data = json.loads(html_mod.unescape(m.group(2)))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _order_blocks(page: str) -> list[str]:
    for pattern in (ORDER_HEADER, ORDER_SECTION):
        starts = [m.start() for m in pattern.finditer(page)]
        if starts:
            return [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])]
    return []


def _first_class_text(block: str, names: str) -> str:
    m = re.search(
        r"""<\w+\b[^>]*\bclass\s*=\s*["'][^"']*(?:%s)[^"']*["'][^>]*>(.*?)</""" % names,
        block, re.S | re.I,
    )
    return text(m.group(1)) if m else ""


def _order_number(block: str, body: str) -> Optional[str]:
    value = _first_class_text(block, r"order-number|orderNo|order-no")
    if value:
        m = re.search(r"([A-Z0-9][A-Z0-9-]{5,})", value, re.I)
        if m:
            return m.group(1)
    m = ORDER_NUMBER.search(body)
    if m:
        return m.group(1)
    m = ORDER_NUMBER_QS.search(block)
    if m:
        return m.group(1)
    return None


def _order_date(block: str, body: str) -> Optional[str]:
    value = _first_class_text(block, r"date-time|date")
    m = ORDER_DATE.search(value or body)
    return m.group(0) if m else None


def _order_total(block: str, body: str) -> Optional[str]:
    m = ORDER_TOTAL.search(body)
    if m:
        return m.group(1) + " €"
    value = _first_class_text(block, r"\bprice\b")
    m = re.search(r"(\d+[.,]\d{2})\s*€", value)
    if m:
        return m.group(1) + " €"
    amounts = re.findall(r"(\d+[.,]\d{2})\s*€", body)
    return amounts[-1] + " €" if amounts else None


def _order_status(block: str, body: str) -> Optional[str]:
    value = _first_class_text(block, r"\bstatus\b")
    if value:
        return value
    m = KNOWN_STATUSES.search(body)
    return m.group(1) if m else None


def _order_items(block: str) -> list[str]:
    names: list[str] = []
    for pattern in (r"<h3\b[^>]*>(.*?)</h3>",
                    r"<h4\b[^>]*\bclass\s*=\s*[\"'][^\"']*product__title[^\"']*[\"'][^>]*>(.*?)</h4>"):
        for m in re.finditer(pattern, block, re.S | re.I):
            name = text(m.group(1))
            if name and name not in names:
                names.append(name)
    return names[:50]


def _absolute(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return "https://www.sklavenitis.gr" + href


def _cell_total(cell: str) -> Optional[str]:
    value = _first_class_text(cell, r"\bprice\b")
    if value:
        return value if "€" in value else value + " €"
    m = re.search(r"(\d+[.,]\d{2})\s*€", text(cell))
    return m.group(0) if m else None


def _cell_status(cell: str) -> Optional[str]:
    m = re.search(r"<span\b[^>]*>(.*?)</span>", cell, re.S | re.I)
    if m:
        value = text(m.group(1))
        if value:
            return value
    value = text(cell)
    value = re.sub(r"^\s*Κατάσταση\s*", "", value)
    return value or None


def _order_table_rows(page: str) -> list[dict[str, Any]]:
    """The order-history list: a table with one row per order."""
    orders: list[dict[str, Any]] = []
    for table in ORDER_TABLE.finditer(page):
        for row in ORDER_TR.finditer(table.group(1)):
            cells = [m.group(1) for m in ORDER_TD.finditer(row.group(1))]
            if len(cells) < 5:
                continue
            href = None
            m = re.search(r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
                          cells[0], re.S | re.I)
            if m:
                href = _absolute(m.group(1))
                number = text(m.group(2))
            else:
                number = ""
            if not number:
                q = ORDER_NUMBER_QS.search(cells[0])
                if q:
                    number = q.group(1)
            if not number:
                m = re.search(r"([A-Z0-9][A-Z0-9-]{5,})", text(cells[0]), re.I)
                if m:
                    number = m.group(1)
            if not number:
                continue
            date = _first_class_text(cells[1], r"date-time|date")
            if not date:
                m = ORDER_DATE.search(text(cells[1]))
                date = m.group(0) if m else None
            orders.append({
                "number": number,
                "date": date,
                "total": _cell_total(cells[3]),
                "status": _cell_status(cells[4]),
                "detail_url": href,
                "items": [],
            })
    return orders


def parse_order_detail(page: str) -> dict[str, Any]:
    """One order page: the header plus its product rows."""
    header = parse_orders(page)
    order = header[0] if header else {
        "number": None, "date": None, "total": None, "status": None,
    }
    items: list[dict[str, Any]] = []
    for m in ORDER_ITEM_ROW.finditer(page):
        row = m.group(1)
        link = re.search(
            r"""<h4\b[^>]*\bclass\s*=\s*["'][^"']*horizontal-products__title[^"']*["'][^>]*>
                \s*<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
            row, re.S | re.I | re.X,
        )
        if not link:
            link = re.search(
                r"""<h4\b[^>]*\bclass\s*=\s*["'][^"']*product__title[^"']*["'][^>]*>
                    \s*<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
                row, re.S | re.I | re.X,
            )
        if not link:
            continue
        name = text(link.group(2))
        if not name:
            continue
        sku = None
        m = re.search(r"(\d{5,})/?$", link.group(1))
        if m:
            sku = m.group(1)
        quantity_txt = _first_class_text(row, r"quantTxt|quantityNumber")
        quantity = greek_number(quantity_txt) if quantity_txt else None
        price_txt = _cell_total(row)
        line_total = greek_number(price_txt) if price_txt else None
        items.append({
            "name": name,
            "sku": sku,
            "quantity": quantity,
            "price": price_txt,
            "line_total": line_total,
            "unit_price": round(line_total / quantity, 2)
            if line_total is not None and quantity else None,
        })
    order["items"] = items
    return order


def parse_orders(page: str, options: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    rows = _order_table_rows(page)
    if rows:
        return rows

    options = options or {}
    fallback = options.get("CurrentOrder")
    orders: list[dict[str, Any]] = []
    for index, block in enumerate(_order_blocks(page)):
        body = text(block)
        number = _order_number(block, body)
        if not number and index == 0 and fallback:
            number = str(fallback)
        orders.append({
            "number": number,
            "date": _order_date(block, body),
            "total": _order_total(block, body),
            "status": _order_status(block, body),
            "items": _order_items(block),
        })

    if not orders and fallback:
        body = text(page)
        orders.append({
            "number": str(fallback),
            "date": _order_date(page, body),
            "total": _order_total(page, body),
            "status": _order_status(page, body),
            "items": _order_items(page),
        })

    # A list page can repeat an order header; keep one entry per order number.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for order in orders:
        key = order.get("number")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(order)
    return unique


# ------------------------------------------------------------------------ slots

def parse_slots(page: str) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for m in SLOT_TAG.finditer(page):
        tag = m.group(0)
        classes = attr(tag, "class") or ""
        if "date__disabled" in classes:
            continue
        start = attr(tag, "data-starttime")
        end = attr(tag, "data-endtime")
        if not start or not end:
            continue
        slots.append({
            "start": start,
            "end": end,
            "display": attr(tag, "data-display"),
            "date": attr(tag, "data-date"),
            "timespan": attr(tag, "data-timespan"),
        })
    return slots


def slot_form_fields(page: str) -> dict[str, str]:
    hidden = hidden_inputs(page)
    return {
        "RequiresNotification": hidden.get("RequiresNotification", "True"),
        "Notification": hidden.get("Notification", ""),
    }
