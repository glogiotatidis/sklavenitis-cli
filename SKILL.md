---
name: sklavenitis
description: Search Sklavenitis.gr, inspect delivery slots, and manage a real cart (guest or logged in) from the terminal. Use when a user asks to find groceries at Sklavenitis, add/remove/change quantities in their Sklavenitis cart, or check the next delivery date. Every command supports --json.
---

# Sklavenitis shopping

`sklavenitis` is a dependency-free CLI for [Sklavenitis.gr](https://www.sklavenitis.gr). It uses
the site's own session cookies, so it operates the user's real cart and order history. Guest carts
work without an account; `auth login` or a cookie import switches to the account.

## Before the first cart command

1. Check state:

   ```bash
   sklavenitis auth status --json
   sklavenitis address show --json
   sklavenitis delivery --json
   ```

2. If there is no delivery address, set one. Use a street and number or a postal code; the site's
   lookup returns the canonical address, postal code and coordinates:

   ```bash
   sklavenitis address set "Ερμού 1, Αθήνα" --json
   ```

   If several candidates come back, `--pick N` chooses one (1-based).

3. The site requires a delivery slot before the first item is added. **Do not ask the user which
   date first**: `cart add` defaults to the nearest enabled slot. Call `delivery --json` when the
   user explicitly wants alternatives, and `delivery set N` to change it.

## Commands

```bash
sklavenitis search "γάλα" -n 10 --json
sklavenitis search "αλεύρι" -s cheapest --json
sklavenitis orders -n 10 --json                   # requires login
sklavenitis order <number> --json                 # one order with products
sklavenitis cart --json
sklavenitis cart add 1709870 -q 2 --json          # additive; SKU or URL; nearest slot by default
sklavenitis cart add 1709870 -q 2 --slot 3 --json # slot 3 from `delivery --json` (1-based)
sklavenitis cart set 1709870 -q 3 --json          # absolute quantity, not a delta
sklavenitis cart remove 1709870 --json
sklavenitis cart clear --json
sklavenitis delivery --json
sklavenitis delivery set 1 --json
sklavenitis auth status --json
sklavenitis auth login --json                     # prompts; or pass --email/--password
sklavenitis auth import --cookie '<Cookie header>' --json
sklavenitis auth logout --json
```

`--json` goes on the command or subcommand (`sklavenitis cart --json`,
`sklavenitis cart add 1709870 --json`). Errors are `{"error": "..."}` on stderr with exit code
`2`; a search with no results exits `1`.

## Reading the JSON

- `search` → `{query, count, total, results: [{sku, name, price, unit, step, max_quantity,
  available, not_buyable, url}]}`. `price` is EUR per `unit`; `step` is the quantity increment
  (some products are weighted, e.g. 0.5 kg). Use `sku` for cart commands. Check `available > 0`
  and `not_buyable == false` before adding; the site also enforces stock at mutation time.
- `cart` → `{authenticated, address, slot, summary, items}`. `summary.total` is the site's
  formatted total string; `items[].quantity` is a number, `unit_price` and `line_total` are
  numbers. `slot.with_day` is the human delivery window.
- `cart add|set|remove|clear` → `{ok, action, sku, quantity, result, cart}`. `quantity` is the
  final line quantity (`0` for remove, `null` for clear); `cart add` also has `added_quantity`,
  the amount requested. The nested `cart` is the post-mutation state; report from it rather than
  guessing.
- `delivery` → `{current, saved, address, nearest, slots: [{start, end, display, date,
  timespan}]}`. `nearest` is `slots[0]`; `start`/`end` are ISO-like `YYYY-MM-DD HH:MM:SS`.
- `orders` → `{count, orders: [{number, date, total, status, detail_url, items}], has_more}`.
  Requires login; list rows have `items: []`, and `detail_url` is the order page.
- `order <number|url>` → `{order: {number, date, total, status, items}, url}`. Items are
  `{name, sku, quantity, price, line_total, unit_price}`; `price` is the site’s display string and
  the other two are numbers. The parser is tolerant of the site’s markup, so a missing field is
  `null`, not a reason to invent one.
- `auth status` → `{authenticated, cookies, config, address}`. `authenticated: false` means the
  guest cart.

## Rules for assistants

- Read `cart --json` before mutating if the user asks for a relative change; `cart set` is
  absolute, so compute the target quantity from the current `items[].quantity`.
- Confirm with the user before `cart clear` or removing many lines. `cart set` and `cart remove`
  are idempotent, so a timeout can be retried.
- `cart add` is **additive**. After a timeout or an ambiguous failure, read `cart --json` and
  compare the line quantity before retrying; a blind retry can double the quantity.
- Never print, log, or commit the Cookie header, `cookies.json`, `config.json`, or a captured
  `.har`. The session is personal data.
- If `auth login` fails, do not retry with the same password. Report the reCAPTCHA message and
  offer the browser cookie import (`auth import`), which is the supported fallback.
- If `cart add` returns an address error, set an address once; if it returns a slot error, run
  `delivery` and choose a valid slot. The first add is slower because it walks the guest wizard.
- Do not invent prices, totals, availability, or delivery dates. Those fields come from the JSON.
- The site is Greek; product names and slot labels are Greek. Preserve them.

## Exit codes

- `0` success
- `1` search returned no results
- `2` usage, auth, transport, or site error (JSON error object on stderr)
- `130` interrupted

## Install (for the operator)

```bash
pipx install .
# or from a checkout:
python3 -m venv .venv && .venv/bin/pip install -e .
```

State lives in `~/.config/sklavenitis-cli/` (override `SKLAVENITIS_CONFIG_DIR`). Set
`SKLAVENITIS_EMAIL` / `SKLAVENITIS_PASSWORD` to avoid prompts; a login token can be supplied with
`SKLAVENITIS_RECAPTCHA_TOKEN` or `--recaptcha-token`.
