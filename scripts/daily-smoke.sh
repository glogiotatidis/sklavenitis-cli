#!/usr/bin/env bash
# Daily live account smoke: login -> search -> add -> set -> remove -> orders -> logout.
#
# Mutates only a SKU that is not already in the cart, then removes it. A trap
# removes it and logs out even when a step fails.
set -euo pipefail

: "${SKLAVENITIS_EMAIL:?SKLAVENITIS_EMAIL is required}"
: "${SKLAVENITIS_PASSWORD:?SKLAVENITIS_PASSWORD is required}"

CFG=$(mktemp -d)
export SKLAVENITIS_CONFIG_DIR="$CFG"
ADDED=0
LOGGED_OUT=0
SKU=""

cleanup() {
    if [ "$ADDED" -eq 1 ] && [ -n "$SKU" ]; then
        sklavenitis cart remove "$SKU" --json >/dev/null 2>&1 || true
    fi
    if [ "$LOGGED_OUT" -eq 0 ]; then
        sklavenitis auth logout --json >/dev/null 2>&1 || true
    fi
    rm -rf "$CFG"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "== login"
sklavenitis auth login --json >"$CFG/login.json"
jq -e '.authenticated == true' "$CFG/login.json" >/dev/null

sklavenitis auth status --json >"$CFG/status.json"
jq -e '.authenticated == true' "$CFG/status.json" >/dev/null
echo "login ok"

echo "== delivery"
sklavenitis delivery --json >"$CFG/delivery.json"
jq -e '(.slots | type) == "array"' "$CFG/delivery.json" >/dev/null

echo "== address"
sklavenitis address show --json >"$CFG/address.json"
jq -e 'has("address")' "$CFG/address.json" >/dev/null

echo "== search"
sklavenitis search "νερό" -n 20 --json >"$CFG/search.json"
jq -e '.count > 0' "$CFG/search.json" >/dev/null

echo "== cart snapshot"
sklavenitis cart --json >"$CFG/cart-before.json"

# Pick an in-stock product that is not already in the cart, so removing it
# restores the account's cart exactly.
mapfile -t CANDIDATES < <(jq -r --slurpfile cart "$CFG/cart-before.json" '
  [.results[]
   | select((.available // 0) > 0)
   | select(.not_buyable == false)
   | select(.sku as $s | ($cart[0].items | map(.sku) | index($s)) == null)
   | .sku] | .[:5][]' "$CFG/search.json")

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
    echo "no in-stock product outside the cart was found" >&2
    exit 1
fi

echo "== add"
for candidate in "${CANDIDATES[@]}"; do
    if sklavenitis cart add "$candidate" -q 1 --json >"$CFG/add.json" 2>"$CFG/add.err"; then
        SKU="$candidate"
        ADDED=1
        break
    fi
    echo "candidate $candidate was rejected; trying the next one"
done
if [ "$ADDED" -ne 1 ]; then
    cat "$CFG/add.err" >&2
    echo "could not add any candidate" >&2
    exit 1
fi
jq -e '.ok == true and (.quantity >= 1)' "$CFG/add.json" >/dev/null

echo "== set quantity"
sklavenitis cart set "$SKU" -q 2 --json >"$CFG/set.json"
jq -e '.ok == true and .quantity == 2' "$CFG/set.json" >/dev/null

echo "== remove"
sklavenitis cart remove "$SKU" --json >"$CFG/remove.json"
jq -e '.ok == true and .quantity == 0' "$CFG/remove.json" >/dev/null
ADDED=0

echo "== orders"
sklavenitis orders -n 5 --json >"$CFG/orders.json"
jq -e '(.orders | type) == "array" and .count >= 1 and .count == (.orders | length)' \
    "$CFG/orders.json" >/dev/null
ORDER_COUNT=$(jq -r '.count' "$CFG/orders.json")
echo "orders visible: $ORDER_COUNT"

echo "== order detail"
ORDER_NUMBER=$(jq -r '.orders[0].number' "$CFG/orders.json")
sklavenitis order "$ORDER_NUMBER" --json >"$CFG/order.json"
jq -e '(.order.items | type) == "array" and (.order.number != null)' "$CFG/order.json" >/dev/null

echo "== logout"
sklavenitis auth logout --json >"$CFG/logout.json"
jq -e '.ok == true' "$CFG/logout.json" >/dev/null
LOGGED_OUT=1

sklavenitis auth status --json >"$CFG/status-after.json"
jq -e '.authenticated == false' "$CFG/status-after.json" >/dev/null

echo "account smoke ok"
