# Closes report the executed deal, not the raw acknowledgement

Related: #89 (async fill price on `/order`), qkt#1092.

## Problem

Dealer-desk servers (The5ers' FivePercentOnline) acknowledge a trade with
`TRADE_RETCODE_DONE` while `price` and `deal` are still `0`; the deal lands in
history moments later. `/order` waits for it since #89. The close routes relay
the raw result. On 2026-09-24 16:00 UTC a strategy exit on a live The5ers
account came back as price 0.0 / deal 0, qkt booked the close at 0 (realized
-4,366 on 0.01 lot of gold, venue truth -107.79), the book breached its daily
drawdown limit and flattened five more positions, each also relayed at 0.

A second fault in the same path: `GET /history_deals_get?position=N` passes the
date range and `position` together to `mt5.history_deals_get`, which ignores
`position` when dates are given. The route returns every deal in the range, so
a consumer that trusts the filter reads other positions' deals.

## Behaviour

- `POST /close_position`, `POST /position_close_partial` and each entry of
  `POST /close_all_positions`: when the successful result carries no price or no
  deal ticket, the gateway polls for the position's closing deal (the deal named
  by the result if any, else the position's `OUT`/`INOUT`/`OUT_BY` deal matching
  the result's order ticket, else its newest such deal) for up to
  `MT5_FILL_CONFIRM_TIMEOUT_MS` (default 3000) every `MT5_FILL_CONFIRM_POLL_MS`
  (default 200), the same knobs as `/order`. When found, `result.price`,
  `result.deal` (and a missing `result.volume`) are replaced with the deal's.
- Each close response carries `fill_price_source`: `order_send` (the server
  reported both), `deal` (confirmed from history) or `unresolved` (the raw result
  is relayed; logged as a WARNING).
- A server that reports price and deal on the acknowledgement (Exness, IC
  Markets) makes no extra MT5 call.
- `GET /history_deals_get` with `position` queries MT5 by position alone and
  keeps the deals whose time falls inside `[from_date, to_date]`.

## Out of scope

Consumer-side handling of an `unresolved` close (qkt must never book price 0;
tracked in qkt).
