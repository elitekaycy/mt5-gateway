"""Confirm what a close actually executed at.

Dealer-desk servers (The5ers' FivePercentOnline) acknowledge a close with
TRADE_RETCODE_DONE while price and deal are still 0; the closing deal lands in
history moments later. Relayed raw, that 0 made qkt book an entry-sized loss and
flatten a live book (2026-09-24). `/order` waits for its fill the same way (#89).
"""

import logging
import os
import time
from typing import Any, Optional

from mt5_connection import mt5

logger = logging.getLogger(__name__)

CLOSE_CONFIRM_TIMEOUT_MS = int(os.getenv("MT5_FILL_CONFIRM_TIMEOUT_MS", "3000"))
CLOSE_CONFIRM_POLL_MS = int(os.getenv("MT5_FILL_CONFIRM_POLL_MS", "200"))

# DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY: deals that reduce a position.
_CLOSING_ENTRIES = (1, 2, 3)


def closing_deal(
    position_ticket: int, order_ticket: int = 0, deal_ticket: int = 0
) -> Optional[dict[str, Any]]:
    """The deal that executed a close of `position_ticket`, as a dict, or None.

    Prefers the deal the result named; else the position's closing deal placed by
    `order_ticket`; with no order ticket, the position's newest closing deal. MT5
    ignores `position` when a date range is also given, so query by position alone.
    """
    if deal_ticket:
        deals = mt5.history_deals_get(ticket=deal_ticket)
        if deals and deals[0].price:
            named: dict[str, Any] = deals[0]._asdict()
            return named
    closing = [
        deal._asdict()
        for deal in mt5.history_deals_get(position=position_ticket) or ()
        if deal.entry in _CLOSING_ENTRIES and deal.price
    ]
    if order_ticket:
        closing = [deal for deal in closing if deal["order"] == order_ticket]
    return max(closing, key=lambda deal: deal["time_msc"], default=None)


def confirm_close(
    result_dict: dict[str, Any], position_ticket: int, request_id: Optional[str]
) -> str:
    """Fill in a close result's missing price and deal from history.

    Mutates `result_dict` and returns where its price came from: `order_send`
    (the server reported both), `deal` (confirmed from history) or `unresolved`.
    """
    if result_dict.get("price") and result_dict.get("deal"):
        return "order_send"
    deadline = time.monotonic() + CLOSE_CONFIRM_TIMEOUT_MS / 1000.0
    while True:
        try:
            deal = closing_deal(
                position_ticket,
                order_ticket=result_dict.get("order") or 0,
                deal_ticket=result_dict.get("deal") or 0,
            )
        except Exception as exc:  # a lookup failure must not fail the close response
            logger.debug(f"[{request_id}] closing-deal lookup retry after: {exc}")
            deal = None
        if deal:
            result_dict["price"] = deal["price"]
            result_dict["deal"] = deal["ticket"]
            if not result_dict.get("volume"):
                result_dict["volume"] = deal["volume"]
            logger.info(
                f"[{request_id}] close of position {position_ticket} confirmed from deal "
                f"{deal['ticket']} at {deal['price']}"
            )
            return "deal"
        if time.monotonic() >= deadline:
            break
        time.sleep(CLOSE_CONFIRM_POLL_MS / 1000.0)
    logger.warning(
        f"[{request_id}] close of position {position_ticket} unconfirmed after "
        f"{CLOSE_CONFIRM_TIMEOUT_MS}ms; relaying price={result_dict.get('price')} deal={result_dict.get('deal')}"
    )
    return "unresolved"
