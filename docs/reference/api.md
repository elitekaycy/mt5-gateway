# API

Interactive docs — every endpoint, its parameters, and example
responses — are at `http://localhost:5001/apidocs` once the gateway is
running. That page is generated from the Flask app itself
(`app/swagger.py`), so it's always in sync with the deployed code; this page
covers the conventions that apply across all of it.

## Response envelope

Every JSON response includes `ok`.

- Collection responses use `data`.
- Successful mutations also include a human-readable `message`, the broker
  `result`, and operation-specific safety fields.
- Errors include `ok: false`, `error`, and `error_type`, with optional
  `details`, `request_id`, and `mt5_error`.

## Idempotency

Send a stable `Idempotency-Key` header (or a matching `client_order_id` body
field) with every trade request. Repeating the same key and request replays
the original response without placing another order. Reusing a key with
different parameters returns `409`. A `502 unknown_outcome` means the broker
may have accepted the request — reconcile positions and order/deal history
(`GET /reconcile`) before retrying.

## Modifying stop-loss / take-profit

`/modify_sl_tp` preserves the current `sl`/`tp` value when the field is
omitted. Removing protection requires the explicit `clear_sl: true` or
`clear_tp: true` field — an omission is never treated as "remove this."

## Example calls

```bash
# Account
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account

# Symbols
curl -H "Authorization: Bearer $API_KEY" "http://localhost:5001/symbols?search=*EUR*"

# Latest tick
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/symbol_info_tick/EURUSD

# 100 M1 bars of EURUSD
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:5001/fetch_data_pos?symbol=EURUSD&timeframe=M1&num_bars=100"

# Market order
curl -X POST http://localhost:5001/order \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Idempotency-Key: strategy-a-20260703-0001" \
  -d '{"symbol": "EURUSD", "volume": 0.01, "type": "BUY"}'

# Open positions and reconciliation
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/get_positions
curl -H "Authorization: Bearer $API_KEY" "http://localhost:5001/reconcile?magic=12345"
```

Routes live in `app/routes/` — one file per resource
(`order.py`, `position.py`, `data.py`, `history.py`, `symbol.py`,
`account.py`, `control.py`, `health.py`), each registered with the Flask
app in `app/app.py`.
