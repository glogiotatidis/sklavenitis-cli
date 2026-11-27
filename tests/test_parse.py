"""Parser tests on synthetic Sklavenitis fragments (no network, no site data)."""
from __future__ import annotations

from sklavenitis_cli import parse

SEARCH_PAGE = """
<div class="product  prGa_111111 " data-anchortarget="111111"
     data-plugin-product='{"presentation":"tile","sku":"111111","unitDisplay":"τεμ.","step":1,"status":0,"notBuyable":false,"maximum":12.00,"stock":{"available":4.000,"category":0,"receivingDate":0}}'
     data-item='{"ProductID":10,"ProductSKU":"111111"}'>
  <div class="product-options"><div class="product__title">nested must not win</div></div>
  <div class="product_innerTop">
    <figure class="product__figure"><a href="/p/test-one-111111/"><img alt="x"></a></figure>
    <article><h4 class="product__title"><a href="/p/test-one-111111/">TEST PRODUCT ONE</a></h4></article>
  </div>
  <div class="product_innerBtm">
    <div class="product_prices"><div class="price" data-price="1,89">1,89 €</div></div>
  </div>
</div>
<div class="product  prGa_222222 " data-anchortarget="222222"
     data-plugin-product='{"presentation":"tile","sku":"222222","unitDisplay":"κιλό","step":0.5,"status":0,"notBuyable":true,"maximum":9.00,"stock":{"available":0.0,"category":0,"receivingDate":0}}'
     data-item='{"ProductID":20,"ProductSKU":"222222"}'>
  <article><h4 class="product__title"><a href="/p/test-two-222222/">TEST PRODUCT TWO</a></h4></article>
  <div class="price" data-price="12,50">12,50 €</div>
</div>
<div class="pagination go-next" data-pg="2"><span>24 από τα 120 προϊόντα</span></div>
"""

CART_PAGE = """
<div class="product prGa_111111" data-anchortarget="111111"
     data-item='{"ProductID":10,"ProductSKU":"111111"}'>
  <article><h4 class="product__title"><a href="/p/test-one-111111/">TEST PRODUCT ONE</a></h4></article>
  <div class="q2 quantWrap"><span class="remove btn quantity-remove"></span>
    <span class="quantityNumber">2<span class="quantityNumber__text"> τεμ.</span></span></div>
  <div class="price" data-price="1,89">1,89 €</div>
</div>
<div class="product prGa_999999" data-anchortarget="999999"
     data-item='{"ProductID":99,"ProductSKU":"999999"}'>
  <article><h4 class="product__title"><a href="/p/recommendation-999999/">RECOMMENDATION</a></h4></article>
  <div class="price" data-price="3,00">3,00 €</div>
</div>
"""

SLOT_PAGE = """
<form id="promptslotselection">
  <input type="hidden" name="RequiresNotification" value="True" />
  <input type="hidden" name="Notification" value="some products may differ" />
  <div class="date__hours">
    <div class="date__box date__hour date__disabled hours_4"></div>
    <div class="date__box date__hour hours_14"
         data-date="28/11/2026 12:00:00 πμ"
         data-timespan="07:00 - 09:00"
         data-starttime="2026-11-28 07:00:00"
         data-endtime="2026-11-28 09:00:00"
         data-display="Σάββατο 28 Νοεμβρίου 2026, 07:00 - 09:00"></div>
    <div class="date__box date__hour hours_14"
         data-date="28/11/2026 12:00:00 πμ"
         data-timespan="09:00 - 11:00"
         data-starttime="2026-11-28 09:00:00"
         data-endtime="2026-11-28 11:00:00"
         data-display="Σάββατο 28 Νοεμβρίου 2026, 09:00 - 11:00"></div>
  </div>
</form>
"""

ORDER_PAGE = """
<div data-plugin-orderhistory="{&quot;CurrentOrder&quot;:&quot;ABCDEF123456&quot;,
     &quot;PreviousOrder&quot;:&quot;AAAAAAAAAAAA&quot;,
     &quot;PreviousOrderUrl&quot;:&quot;/account/istoriko-paraggelion/?OrderNumber=AAAAAAAAAAAA&quot;}">
  <section class="order-list">
    <div class="order-header">
      <div class="order-header__left"><span class="date-time">26/11/2026 10:30</span></div>
      <div class="order-header__center"><span class="order-number">ABCDEF123456</span></div>
      <div class="order-header__right"><span class="price">45,20 €</span></div>
      <div class="status">Ολοκληρώθηκε</div>
    </div>
    <div class="table product"><h3>TEST PRODUCT ONE</h3></div>
    <div class="table product"><h3>TEST PRODUCT TWO</h3></div>
  </section>
</div>
"""

ORDER_TABLE_PAGE = """
<table class="table-order table-sticky-header">
  <thead><tr><th class="table-order__code"><div class="table__th">Κωδικός Παραγγελίας</div></th></tr></thead>
  <tbody>
    <tr>
      <td><div class="table-order__title">Κωδικός Παραγγελίας</div>
          <a href="/account/istoriko-paraggelion/?OrderNumber=ABCDEF123456">ABCDEF123456</a></td>
      <td><div class="table-order__title">Χρόνος Παράδοσης</div>
          <div class="date-time">17/11/2026</div></td>
      <td><div class="table-order__title">Διεύθυνση Παράδοσης</div>
          <address>TEST ADDRESS</address></td>
      <td><div class="table-order__title">Αξία</div>
          <div class="table-order__price price">45,20 €</div></td>
      <td class="table-order__centered"><div class="table-order__title">Κατάσταση</div>
          <span>Έχει παραδοθεί</span></td>
      <td class="table-order__centered"><span>repeat</span></td>
    </tr>
  </tbody>
</table>
"""

ORDER_DETAIL_PAGE = """
<div class="order-header">
  <div class="order-header__wrapper"><div class="order-header__content">
    <div class="order-header__left">
      <div class="order-header__title">Χρόνος Παράδοσης</div>
      <div class="date-time">17/11/2026</div>
    </div>
    <div class="order-header__center">
      <div class="order-header__title">Κωδικός Παραγγελίας</div>
      <div class="order-number">ABCDEF123456</div>
      <div class="status">Έχει παραδοθεί</div>
    </div>
    <div class="order-header__right">
      <div class="order-header__title">Αξία</div>
      <div class="price">45,20 €</div>
    </div>
  </div></div>
</div>
<section class="cart history">
  <table><tbody>
    <tr class="product horizontal-products__tr">
      <td class="product-td"><div class="horizontal-products__product"><article>
        <h4 class="horizontal-products__title"><a href="/p/test-product-111111/">TEST PRODUCT ONE</a></h4>
      </article></div></td>
      <td class="quant-td"><div class="quantTxt">2 τεμ.</div></td>
      <td class="priceWrp"><div class="price">3,78 €</div></td>
    </tr>
    <tr class="product horizontal-products__tr">
      <td class="product-td"><div class="horizontal-products__product"><article>
        <h4 class="horizontal-products__title"><a href="/p/test-product-222222/">TEST PRODUCT TWO</a></h4>
      </article></div></td>
      <td class="quant-td"><div class="quantTxt">1 τεμ.</div></td>
      <td class="priceWrp"><div class="price">1,89 €</div></td>
    </tr>
  </tbody></table>
</section>
"""

LOGIN_PAGE = '<form id="Login"><input name="__RequestVerificationToken" type="hidden" value="tok" /></form>'
ADDRESS_PAGE = '<form class="zipCode"><input data-role-addressform="ZipCode" name="ZipCode" /></form>'


def test_search_products_and_total() -> None:
    data = parse.parse_search(SEARCH_PAGE)
    assert data["count"] == 2
    assert data["total"] == 120
    first = data["products"][0]
    assert first["sku"] == "111111"
    assert first["name"] == "TEST PRODUCT ONE"
    assert first["price"] == 1.89
    assert first["available"] == 4.0
    assert first["url"] == "https://www.sklavenitis.gr/p/test-one-111111/"
    second = data["products"][1]
    assert second["step"] == 0.5
    assert second["not_buyable"] is True


def test_cart_only_counts_lines_with_a_quantity_widget() -> None:
    items = parse.parse_cart_items(CART_PAGE)
    assert len(items) == 1
    assert items[0]["sku"] == "111111"
    assert items[0]["quantity"] == 2
    assert items[0]["unit_price"] == 1.89
    assert items[0]["line_total"] == 3.78


def test_slots_skip_disabled_and_are_chronological() -> None:
    slots = parse.parse_slots(SLOT_PAGE)
    assert [s["start"] for s in slots] == ["2026-11-28 07:00:00", "2026-11-28 09:00:00"]
    assert slots[0]["display"].startswith("Σάββατο")
    assert parse.slot_form_fields(SLOT_PAGE) == {
        "RequiresNotification": "True",
        "Notification": "some products may differ",
    }


def test_form_detection_and_token() -> None:
    assert parse.is_login_form(LOGIN_PAGE)
    assert parse.is_address_form(ADDRESS_PAGE)
    assert parse.is_slot_form(SLOT_PAGE)
    assert parse.form_token(LOGIN_PAGE) == "tok"
    assert not parse.is_login_form(ADDRESS_PAGE)


def test_order_options_and_order_fields() -> None:
    options = parse.parse_order_options(ORDER_PAGE)
    assert options["CurrentOrder"] == "ABCDEF123456"
    assert options["PreviousOrderUrl"].endswith("OrderNumber=AAAAAAAAAAAA")
    orders = parse.parse_orders(ORDER_PAGE, options)
    assert len(orders) == 1
    order = orders[0]
    assert order["number"] == "ABCDEF123456"
    assert order["date"] == "26/11/2026 10:30"
    assert order["total"] == "45,20 €"
    assert order["status"] == "Ολοκληρώθηκε"
    assert order["items"] == ["TEST PRODUCT ONE", "TEST PRODUCT TWO"]


def test_order_table_rows() -> None:
    orders = parse.parse_orders(ORDER_TABLE_PAGE)
    assert len(orders) == 1
    order = orders[0]
    assert order["number"] == "ABCDEF123456"
    assert order["date"] == "17/11/2026"
    assert order["total"] == "45,20 €"
    assert order["status"] == "Έχει παραδοθεί"
    assert order["detail_url"].endswith("OrderNumber=ABCDEF123456")
    assert order["items"] == []


def test_order_detail_items() -> None:
    order = parse.parse_order_detail(ORDER_DETAIL_PAGE)
    assert order["number"] == "ABCDEF123456"
    assert order["date"] == "17/11/2026"
    assert order["total"] == "45,20 €"
    assert order["status"] == "Έχει παραδοθεί"
    assert len(order["items"]) == 2
    first = order["items"][0]
    assert first["name"] == "TEST PRODUCT ONE"
    assert first["sku"] == "111111"
    assert first["quantity"] == 2
    assert first["price"] == "3,78 €"
    assert first["line_total"] == 3.78
    assert first["unit_price"] == 1.89


def test_order_fallback_uses_options_without_header() -> None:
    page = '<div data-plugin-orderhistory=\'{"CurrentOrder":"ABCDEF123456"}\'>' \
           '<span class="status">Σε εξέλιξη</span><span class="price">3,50 €</span></div>'
    options = parse.parse_order_options(page)
    orders = parse.parse_orders(page, options)
    assert len(orders) == 1
    assert orders[0]["number"] == "ABCDEF123456"
    assert orders[0]["total"] == "3,50 €"


def test_greek_number() -> None:
    assert parse.greek_number("1.234,56 €") == 1234.56
    assert parse.greek_number("1,89") == 1.89
    assert parse.greek_number("—") is None
