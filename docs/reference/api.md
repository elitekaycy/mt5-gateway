# API

Interactive docs — every endpoint, its parameters, and example
responses — are at `http://localhost:5001/apidocs` once the gateway is
running. That page is generated from the Flask app itself
(`app/swagger.py`) and served from the running container, so it matches the
version you deployed; this page lists the routes and the conventions that apply
across all of them.

## Routes

Every route below needs the bearer token when `API_KEY` is set, except `GET /health/live`
and the Swagger assets. Parameters are the required ones; Swagger lists the rest.

| Method and path | Purpose |
|---|---|
| `GET /health/live` | Process liveness. No auth. |
| `GET /health/ready` | `200` when the terminal and account answer, else `503`. |
| `GET /health` | Full status: `mt5_status`, `uptime_seconds`, `kill_switch_active`, `version`, `mt5_account`, `last_error`, `server_time`. |
| `GET /metrics` | Prometheus text counters. |
| `GET /account` | Account info. |
| `GET /symbols?search=` | Symbol list; `search` is a pattern such as `*EUR*` (default `*`). |
| `GET /symbol_info/<symbol>`, `GET /symbol_info_tick/<symbol>` | Symbol properties; latest tick. |
| `GET /fetch_data_pos?symbol=&timeframe=&num_bars=` | Latest bars (`timeframe` default `M1`, `num_bars` default `100`, capped by `MAX_NUM_BARS`). |
| `GET /fetch_data_range?symbol=&start=&end=&timeframe=` | Bars in an ISO date range (capped by `MAX_HISTORY_RANGE_DAYS`). |
| `GET /copy_ticks_range?symbol=&from_date=&to_date=&flags=` | Raw ticks in a range. |
| `POST /order` | Market or pending order. Body needs `symbol`, `volume`, `type`; `price` for pending types; optional `sl`, `tp`, `deviation`, `magic`, `comment`, `type_filling`, `expiration` (unix seconds, makes it GTD), `client_order_id`. |
| `POST /order_check` | Native pre-trade check of an order without sending it. |
| `POST /order_calc_margin`, `POST /order_calc_profit` | Margin and profit calculators. Margin needs `symbol`, `volume`, `type`, `price`; profit also `price_open`, `price_close`. |
| `GET /orders?symbol=&ticket=` | Pending orders (not positions). |
| `PUT /orders/<ticket>`, `DELETE /orders/<ticket>` | Modify or cancel a pending order. |
| `GET /get_positions?magic=`, `GET /positions_total` | Open positions; their count. |
| `POST /close_position` | Close one position. Body `{"position": {"ticket": N}}`. |
| `POST /position_close_partial` | Close part of a position. Body `ticket`, `volume`; optional `deviation`, `comment`. |
| `POST /close_all_positions` | Body optional: `order_type` (`BUY`, `SELL` or `all`) and `magic`. Returns `207` when some closes failed. |
| `POST /modify_sl_tp` | Body `position`, plus `sl` and/or `tp`, `clear_sl`, `clear_tp`. |
| `GET /get_deal_from_ticket?ticket=`, `GET /get_order_from_ticket?ticket=` | One deal or order. |
| `GET /history_deals_get?from_date=&to_date=&position=` | Deals in a range; with `position` only that position's deals. |
| `GET /history_orders_get?ticket=` | Historical orders for a ticket. |
| `GET /history_deals_range?from_date=&to_date=&magic=` | Deals in a range, optionally by magic. |
| `GET /reconcile?magic=` | Broker truth: positions, orders and the last 24 hours of deals. |
| `POST /kill`, `POST /kill/release` | Engage or release the kill switch; `POST /kill?flatten=true` also removes pending orders and closes all positions. |
| `GET /last_error`, `GET /last_error_str` | Last MT5 error. |

Dates are ISO 8601; a trailing `Z` is accepted.

## Close responses

`/close_position`, `/position_close_partial` and `/close_all_positions` confirm what a
close executed at. Some dealer-desk servers acknowledge a close with price `0` and deal
`0`; the gateway then reads the position's closing deal from history, waiting up to
`MT5_FILL_CONFIRM_TIMEOUT_MS`. Each close response carries `fill_price_source`:
`order_send` (the server reported it), `deal` (confirmed from history) or
`unresolved`. Treat `unresolved` as unknown, not as a price of 0, and reconcile.
`POST /order` carries the same `fill_price_source` field.

## Kill switch and writes

While the kill switch is engaged, `POST /order`, `/modify_sl_tp`,
`/position_close_partial`, `/close_position` and `/close_all_positions` return `423`
with `error_type: kill_switch_active`. Reads, `/reconcile`, `/kill` and `/kill/release`
keep working.

## Response envelope

Every JSON response includes `ok` and, when present, the `request_id` (also sent as the
`X-Request-ID` header; send your own `X-Request-ID` to have it echoed).

- A list result is wrapped as `{"ok": true, "data": [...]}`.
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
