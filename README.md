# sklavenitis-cli

[![tests](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/tests.yml)
[![live](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/live.yml/badge.svg)](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/live.yml)
[![account-live](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/account-live.yml/badge.svg)](https://github.com/glogiotatidis/sklavenitis-cli/actions/workflows/account-live.yml)

[Sklavenitis.gr](https://www.sklavenitis.gr) in the terminal: product search, delivery slots, your
real cart, and order history — guest or logged in. No browser automation, no API key, **no runtime
dependencies**; the package talks to the site with `urllib` and parses its HTML with the standard
library.

The site requires a delivery address and a delivery slot before the first item lands in the cart.
The CLI handles that: set an address once, then `cart add` defaults to the **nearest available
delivery slot** and walks the guest checkout wizard for you.

## Install

```bash
pipx install git+https://github.com/glogiotatidis/sklavenitis-cli
# or, from a checkout
python3 -m venv .venv && .venv/bin/pip install -e . && ln -s "$PWD/.venv/bin/sklavenitis" /usr/local/bin/sklavenitis
```

Python 3.9+. Nothing else.

## Guest cart in two commands

```bash
sklavenitis address set "Ερμού 1, Αθήνα"    # looks up the address and stores it (0600)
sklavenitis cart add 1709870 -q 2           # first add: address -> nearest slot -> cart
sklavenitis cart                            # items, totals, address, selected slot
```

No account is needed. The cart lives in the cookie jar under
`~/.config/sklavenitis-cli/` (override with `SKLAVENITIS_CONFIG_DIR`), so it survives between
invocations.

## Log in (optional)

```bash
sklavenitis auth login                     # prompts for email/password if not passed
sklavenitis auth status                    # logged in or guest, address, cookie path
sklavenitis auth import --cookie '...'     # paste the Cookie header from a logged-in browser
sklavenitis auth logout                    # POSTs the site's logout and clears local cookies
```

Credentials are never stored. `--email`/`--password` or `SKLAVENITIS_EMAIL`/`SKLAVENITIS_PASSWORD`
avoid the prompt; the password flag is visible in the process list, so prefer the prompt or the
environment.

The login form runs **reCAPTCHA v3**. The CLI posts the form directly and accepts a fresh token
with `--recaptcha-token` (or `SKLAVENITIS_RECAPTCHA_TOKEN`). If the site rejects the automated
login, log in once in a browser and use `auth import`: the CLI never pretends to solve the captcha.
Imported cookies are validated against `/account/` before they replace the current jar, so a bad
paste leaves the existing guest cart or login untouched.

## Search

```bash
sklavenitis search "γάλα"                  # relevance, 10 results
sklavenitis search "γάλα" -n 24            # one full page
sklavenitis search "αλεύρι" -s cheapest    # price ascending
sklavenitis search "καφές" --json          # machine readable, for assistants
sklavenitis orders -n 10                   # order history (requires login)
sklavenitis orders -n 10 --json
sklavenitis order <number>                 # one order with its products
```

Sorts: `relevance`, `cheapest`, `expensive`, `name`, `unit`. The site serves 24 products per page;
`-n` above 24 fetches the following pages.

## Cart

```bash
sklavenitis cart                           # show the cart
sklavenitis cart add 1709870 -q 2          # add 2 (additive); defaults to the nearest slot
sklavenitis cart add <product-url>         # a product URL works too
sklavenitis cart set 1709870 -q 3          # absolute quantity
sklavenitis cart remove 1709870            # remove the line
sklavenitis cart clear                     # remove every line
sklavenitis cart --json                    # one JSON document
```

`cart add --slot N` picks another slot from `sklavenitis delivery` instead of the nearest.

## Delivery

```bash
sklavenitis delivery                       # current slot, address, available slots (nearest first)
sklavenitis delivery set 1                 # select the nearest
sklavenitis delivery set "2026-11-28 15:00:00"
sklavenitis delivery --json
```

A slot is required before the first add. `cart add` selects the nearest enabled slot automatically
if the cart has none; the choice is also saved in `config.json`.

## JSON shapes

`search` → `{query, sort, page, count, total, results: [...]}`. Per product:
`sku, product_id, name, price, unit, step, max_quantity, available, not_buyable, url`.

`cart` → `{authenticated, address, slot, summary, items}`:

```json
{
  "authenticated": false,
  "address": "Ερμού 1, 10563",
  "slot": {"info": "28/11/2026, 15:00 - 17:00", "day": "Σάββατο",
           "with_day": "Σάββατο 28/11/2026, 15:00 - 17:00", "date": 1795870800000,
           "hub": "Πειραιά"},
  "summary": {"items": "2", "total": "3,78 €", "can_checkout": true,
              "minimum_order_reached": false},
  "items": [{"sku": "1709870", "product_id": 273610, "name": "...", "quantity": 2.0,
             "unit_price": 1.89, "line_total": 3.78, "url": "https://..."}]
}
```

`cart add|set|remove|clear` → `{ok, action, sku, quantity, result, cart}`, where `result` is the
site's own mutation response and `cart` is the document above. `quantity` is the **final** line
quantity (`0` for remove, `null` for clear); `cart add` also reports `added_quantity`, the amount
requested. Adding 2 to a line already at 1 yields `quantity: 3`.

`delivery` → `{current, saved, address, nearest, slots: [{start, end, display, date, timespan}]}`.
`nearest` is `slots[0]`, in chronological order.

`orders` → `{count, orders: [{number, date, total, status, detail_url, items}], has_more}`. It
requires a logged-in session; the order-history list is paginated with `pg`. List rows carry an
empty `items` array and a `detail_url`.

`order <number|url>` → `{order: {number, date, total, status, items}, url}`. Each item is
`{name, sku, quantity, price, line_total, unit_price}`; `price` is the site’s display string and
`line_total`/`unit_price` are numbers. Missing fields are `null`, not guessed.

`auth login` → `{authenticated, email}`; `auth status` → `{authenticated, cookies, config, address}`.

Errors with `--json` are `{"error": "..."}` on stderr with exit code `2`. A search with no results
exits `1`.

## Notes that cost time to learn

- Search is server-rendered HTML at `/apotelesmata-anazitisis/?Query=…&sortby=…&pg=…`; there is no
  JSON search endpoint. 24 products per page, total from the `N από τα M` counter.
- A guest's first add is a wizard: login modal → `selectedAction=ContinueAsGuest` → address →
  delivery slot → add. The CLI follows it with `X-UserFlow-New`, `X-NoRedirect` and the site's
  bracketed form keys.
- Cart quantities are **absolute**. `Action=Update` sets a line; `Action=Remove` needs
  `CartItems[0][Quantity]=0`.
- The address form posts Greek-locale coordinates (`37,9755972`, comma decimal), not `37.9755972`.
- Address lookup is `GET /api/Address/Search?term=…` then `GET /api/Address/Details?id=…&text=…`;
  `ZipCodeServed` must be true.
- Selecting a delivery slot is two posts: `TimeSlotChangeUserFlow.TimeSlotSelection/` with the
  antiforgery token, then `TimeSlotChangeUserFlow.Index/` to confirm.
- The login form is reCAPTCHA v3 (`grecaptcha.execute`). The CLI supports a supplied token and
  cookie import instead of bundling a browser. On GitHub-hosted runners the form still rejects the
  direct HTTP login even with a freshly minted token, so the daily job logs in through the real
  form with Playwright and hands the cookies to the CLI (the `auth import` path).
- Sklavenitis sits behind Akamai. From GitHub-hosted runners, `curl` with a Firefox UA still gets
  HTTP 403, while Python `urllib` with the same UA gets 200; a UA with a custom suffix such as
  `sklavenitis-cli/0.1.0` is also rejected. That is why `_http.UA` is a plain browser string with
  no version token, matching the Chrome UA used by the CI browser login. Do not add a suffix, and
  do not replace the transport with `curl` for CI.

## Tests and CI

```bash
pytest                                   # offline: parsers, cart wizard, orders, storage
SKLAVENITIS_LIVE=1 pytest -m live        # real search and address lookup, read-only
```

The offline suite uses synthetic HTML fragments and a scripted session; no network, no account.

Two scheduled workflows:

- **`live.yml`** (05:30 UTC): the read-only live tests against the real search and address
  endpoints.
- **`account-live.yml`** (05:45 UTC): the full account lifecycle in `scripts/daily-smoke.sh` —
  login, status, delivery, address, search, add, set quantity, remove, order history, one order
  detail, logout, and a post-logout status check. `scripts/browser_login.py` uses Playwright and the
  runner's Chrome to submit the real sign-in form and export the session cookies; the CLI itself
  stays dependency-free.

Configure the repository secrets **`SKLAVENITIS_EMAIL`** and **`SKLAVENITIS_PASSWORD`**. Use a
dedicated test account **with at least one past order** — the job asserts `.count >= 1` and then
fetches one order detail, so a broken order-history parser fails the daily run. The job skips with
a warning when the secrets are absent. The script only adds an in-stock SKU that is **not already
in the cart**, sets it to 2, then removes it, so the account's cart is restored. A trap removes the
line and logs out even when a step fails. The browser login is also the early warning that the
site's sign-in flow changed; if it fails, check the credentials and the Playwright login first.

## Layout

```
sklavenitis_cli/_http.py   urllib transport and a persistent cookie jar
sklavenitis_cli/store.py   ~/.config/sklavenitis-cli (cookies 0600, address, slot)
sklavenitis_cli/parse.py   the site's markup: search cards, cart lines, slots, orders
sklavenitis_cli/api.py     endpoints, login, add-to-cart wizard, delivery, orders
sklavenitis_cli/cli.py     argparse surface and human/JSON output
scripts/browser_login.py   CI-only browser login + cookie export for reCAPTCHA v3
scripts/daily-smoke.sh     daily account lifecycle, used by account-live.yml
SKILL.md                   agent skill: when and how to call the CLI
```

If Sklavenitis changes its markup, `parse.py` is the only file to touch; if it changes an endpoint
or a form field, `api.py` is the only file to touch. The CLI surface stays put.

## Security

- Cookies and config are written mode `0600`; passwords are never stored.
- The repository ignores `*.har`, `cookies.json`, `config.json` and `.env`. Do not commit captured
  traffic or a live session.
- `auth logout` clears local cookies; `cart clear` and `cart remove` are explicit and never
  triggered implicitly.

## License

GPL-3.0, see [LICENSE](LICENSE).
