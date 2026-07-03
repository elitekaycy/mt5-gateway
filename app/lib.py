import logging

import pandas as pd

from constants import ORDER_TYPE_TO_STRING, MT5Timeframe
from mt5_connection import mt5
from retcodes import classify_retcode
from time_utils import server_epoch_to_utc

logger = logging.getLogger(__name__)


def get_timeframe(timeframe_str: str) -> MT5Timeframe:
    try:
        return MT5Timeframe[timeframe_str.upper()].value
    except KeyError:
        valid_timeframes = ", ".join([t.name for t in MT5Timeframe])
        raise ValueError(
            f"Invalid timeframe: '{timeframe_str}'. Valid options are: {valid_timeframes}."
        )


def validate_symbol(symbol_name):
    """
    Checks if a symbol exists and is selected in Market Watch.
    If not selected, attempts to select it.
    Returns True if valid/selected, False otherwise.
    """
    if not mt5.symbol_select(symbol_name, True):
        logger.error(f"Failed to select symbol: {symbol_name}")
        return False
    return True


def get_symbol_filling_mode(symbol_name):
    """
    Gets the appropriate filling mode for a symbol.
    Returns the best supported filling mode based on symbol's capabilities.

    Note: ORDER_FILLING_FOK has value 0 which MT5 rejects, so prioritize IOC
    """
    symbol_info = mt5.symbol_info(symbol_name)
    if symbol_info is None:
        logger.error(f"Failed to get symbol info for: {symbol_name}")
        return mt5.ORDER_FILLING_RETURN

    filling_mode = symbol_info.filling_mode

    if filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    elif filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    else:
        return mt5.ORDER_FILLING_RETURN


def close_position(position, deviation=20, magic=0, comment=""):
    if "ticket" not in position:
        logger.error("Position dictionary missing 'ticket' key.")
        return None

    ticket = position["ticket"]
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        logger.error(f"Position {ticket} not found")
        return None

    actual_position = positions[0]

    order_type_dict = {
        0: mt5.ORDER_TYPE_SELL,  # Close BUY position with SELL
        1: mt5.ORDER_TYPE_BUY,  # Close SELL position with BUY
    }

    position_type = actual_position.type
    if position_type not in order_type_dict:
        logger.error(f"Unknown position type: {position_type}")
        return None

    if not validate_symbol(actual_position.symbol):
        logger.error(f"Symbol not found or not selectable: {actual_position.symbol}")
        return None

    tick = mt5.symbol_info_tick(actual_position.symbol)
    if tick is None:
        logger.error(f"Failed to get tick for symbol: {actual_position.symbol}")
        return None

    price_dict = {
        0: tick.bid,  # Close BUY position at Bid
        1: tick.ask,  # Close SELL position at Ask
    }

    price = price_dict[position_type]
    if price == 0.0:
        logger.error(f"Invalid price retrieved for symbol: {actual_position.symbol}")
        return None

    type_filling = get_symbol_filling_mode(actual_position.symbol)
    logger.info(
        f"Closing position {ticket}, symbol={actual_position.symbol}, volume={actual_position.volume}, type={position_type}, order_type={order_type_dict[position_type]}, price={price}, type_filling={type_filling}"
    )

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": actual_position.symbol,
        "volume": actual_position.volume,
        "type": order_type_dict[position_type],
        "price": price,
        "deviation": deviation,
        "magic": actual_position.magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": type_filling,
    }

    order_result = mt5.order_send(request)

    if order_result is None:
        logger.error(
            f"Failed to close position {position['ticket']}: mt5.order_send returned None"
        )
        return None

    if not classify_retcode(order_result.retcode).is_success:
        logger.error(
            f"Failed to close position {position['ticket']}: retcode={order_result.retcode}, comment={order_result.comment}"
        )
        return order_result

    logger.info(f"Position {position['ticket']} closed successfully.")
    return order_result


def close_all_positions(order_type="all", magic=None):
    order_type_dict = {"BUY": mt5.ORDER_TYPE_BUY, "SELL": mt5.ORDER_TYPE_SELL}

    total_positions = mt5.positions_total()
    if total_positions is not None and total_positions > 0:
        positions = mt5.positions_get()
        if positions is None:
            logger.error("Failed to retrieve positions.")
            return {"closed": [], "failed": [{"error": "positions_unavailable"}]}

        positions_data = [pos._asdict() for pos in positions]
        positions_df = pd.DataFrame(positions_data)

        if magic is not None:
            positions_df = positions_df[positions_df["magic"] == magic]

        if order_type != "all":
            if order_type not in order_type_dict:
                logger.error(
                    f"Invalid order_type: {order_type}. Must be 'BUY', 'SELL', or 'all'."
                )
                return {"closed": [], "failed": [{"error": "invalid_order_type"}]}
            positions_df = positions_df[
                positions_df["type"] == order_type_dict[order_type]
            ]

        if positions_df.empty:
            logger.error("No open positions matching the criteria.")
            return {"closed": [], "failed": []}

        closed = []
        failed = []
        for _, position in positions_df.iterrows():
            order_result = close_position(position)
            if order_result is None:
                failed.append(
                    {
                        "ticket": int(position["ticket"]),
                        "retcode": None,
                        "retcode_name": "UNKNOWN_OUTCOME",
                        "comment": "No result returned by MT5",
                    }
                )
            else:
                info = classify_retcode(order_result.retcode)
                result_data = order_result._asdict()
                result_data["partial"] = info.name == "DONE_PARTIAL"
                if info.is_success:
                    closed.append(result_data)
                else:
                    failed.append(
                        {
                            "ticket": int(position["ticket"]),
                            "retcode": order_result.retcode,
                            "retcode_name": info.name,
                            "comment": order_result.comment,
                        }
                    )

        return {"closed": closed, "failed": failed}
    else:
        logger.error("No open positions to close.")
        return {"closed": [], "failed": []}


def get_positions(magic=None):
    total_positions = mt5.positions_total()
    if total_positions is None:
        logger.error("Failed to get positions total.")
        return pd.DataFrame()

    if total_positions > 0:
        positions = mt5.positions_get()
        if positions is None:
            logger.error("Failed to retrieve positions.")
            return pd.DataFrame()

        positions_data = [pos._asdict() for pos in positions]
        positions_df = pd.DataFrame(positions_data)

        if magic is not None:
            positions_df = positions_df[positions_df["magic"] == magic]

        return positions_df
    else:
        return pd.DataFrame(
            columns=[
                "ticket",
                "time",
                "time_msc",
                "time_update",
                "time_update_msc",
                "type",
                "magic",
                "identifier",
                "reason",
                "volume",
                "price_open",
                "sl",
                "tp",
                "price_current",
                "swap",
                "profit",
                "symbol",
                "comment",
                "external_id",
            ]
        )


def get_deal_from_ticket(ticket):
    """
    Get deal information for a position ticket.

    Args:
        ticket: Position ticket number

    Returns:
        Dictionary with deal information or None if not found
    """
    if not isinstance(ticket, int):
        logger.error("Ticket must be an integer.")
        return None

    # Use MT5's native filter to get deals by position ticket
    deals = mt5.history_deals_get(position=ticket)
    if not deals or len(deals) == 0:
        logger.error(f"No deals found for position ticket {ticket}")
        return None

    deal_rows = sorted(
        (deal._asdict() for deal in deals),
        key=lambda deal: (deal["time"], deal.get("time_msc", 0)),
    )
    entries = [deal for deal in deal_rows if deal.get("entry") == mt5.DEAL_ENTRY_IN]
    exits = [
        deal
        for deal in deal_rows
        if deal.get("entry")
        in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT, mt5.DEAL_ENTRY_OUT_BY)
    ]
    opening_deal = entries[0] if entries else deal_rows[0]
    closing_deal = exits[-1] if exits else None

    deal_details = {
        "ticket": ticket,
        "symbol": opening_deal["symbol"],
        "type": "BUY" if opening_deal["type"] == 0 else "SELL",
        "volume": sum(deal["volume"] for deal in entries)
        if entries
        else opening_deal["volume"],
        "open_time": server_epoch_to_utc(opening_deal["time"]).isoformat(),
        "close_time": (
            server_epoch_to_utc(closing_deal["time"]).isoformat()
            if closing_deal
            else None
        ),
        "open_price": opening_deal["price"],
        "close_price": closing_deal["price"] if closing_deal else None,
        "profit": sum(deal.get("profit", 0.0) for deal in deal_rows),
        "commission": sum(deal.get("commission", 0.0) for deal in deal_rows),
        "swap": sum(deal.get("swap", 0.0) for deal in deal_rows),
        "comment": (closing_deal or opening_deal).get("comment", ""),
        "closed": closing_deal is not None,
    }
    return deal_details


def get_order_from_ticket(ticket):
    if not isinstance(ticket, int):
        logger.error("Ticket must be an integer.")
        return None

    # Get the order history
    order = mt5.history_orders_get(ticket=ticket)
    if order is None or len(order) == 0:
        logger.error(f"No order history found for ticket {ticket}")
        return None

    # Convert order to a dictionary
    order_dict = order[0]._asdict()

    return order_dict


def validate_volume(symbol, volume):
    """
    Validate volume against symbol constraints.
    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, "Symbol info unavailable"

    if volume < symbol_info.volume_min:
        return False, f"Volume {volume} below minimum {symbol_info.volume_min}"

    if volume > symbol_info.volume_max:
        return False, f"Volume {volume} exceeds maximum {symbol_info.volume_max}"

    volume_step = symbol_info.volume_step
    if volume_step > 0:
        steps = round((volume - symbol_info.volume_min) / volume_step)
        expected_volume = symbol_info.volume_min + (steps * volume_step)

        epsilon = volume_step * 0.01
        if abs(volume - expected_volume) > epsilon:
            return False, f"Volume must be in steps of {volume_step}"

    return True, None


def validate_sl_tp(order_type, price, sl, tp):
    """
    Validate SL/TP placement relative to order price.
    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    is_buy = order_type in [
        mt5.ORDER_TYPE_BUY,
        mt5.ORDER_TYPE_BUY_LIMIT,
        mt5.ORDER_TYPE_BUY_STOP,
    ]

    if sl is not None:
        if sl <= 0:
            return False, "Stop loss must be positive"

        if is_buy and sl >= price:
            return False, "For BUY orders, SL must be below entry price"
        if not is_buy and sl <= price:
            return False, "For SELL orders, SL must be above entry price"

    if tp is not None:
        if tp <= 0:
            return False, "Take profit must be positive"

        if is_buy and tp <= price:
            return False, "For BUY orders, TP must be above entry price"
        if not is_buy and tp >= price:
            return False, "For SELL orders, TP must be below entry price"

    return True, None


def validate_pending_price(order_type, symbol, price):
    """
    Validate pending order price against current market and freeze level.
    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "Unable to get current price"

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, "Symbol info unavailable"

    freeze_level = symbol_info.trade_freeze_level * symbol_info.point

    type_str = ORDER_TYPE_TO_STRING.get(order_type, "")
    current_price = tick.ask if "BUY" in type_str else tick.bid

    if abs(price - current_price) < freeze_level:
        return False, f"Price too close to market (freeze level: {freeze_level})"

    if order_type == mt5.ORDER_TYPE_BUY_LIMIT and price >= tick.ask:
        return False, "BUY_LIMIT price must be below current ask"

    if order_type == mt5.ORDER_TYPE_SELL_LIMIT and price <= tick.bid:
        return False, "SELL_LIMIT price must be above current bid"

    if order_type == mt5.ORDER_TYPE_BUY_STOP and price <= tick.ask:
        return False, "BUY_STOP price must be above current ask"

    if order_type == mt5.ORDER_TYPE_SELL_STOP and price >= tick.bid:
        return False, "SELL_STOP price must be below current bid"

    return True, None


def validate_type_filling(type_filling_input):
    """
    Validate and convert type_filling to MT5 constant.
    Accepts string values (FOK, IOC, RETURN) or integer constants.
    Returns (mt5_constant, None) if valid, (None, error_message) if invalid.
    """
    TYPE_FILLING_MAP = {
        "FOK": mt5.ORDER_FILLING_FOK,
        "IOC": mt5.ORDER_FILLING_IOC,
        "RETURN": mt5.ORDER_FILLING_RETURN,
    }

    if isinstance(type_filling_input, str):
        type_filling_str = type_filling_input.upper()
        if type_filling_str not in TYPE_FILLING_MAP:
            return (
                None,
                f"Invalid type_filling: {type_filling_input}. Must be one of: FOK, IOC, RETURN",
            )
        return TYPE_FILLING_MAP[type_filling_str], None
    elif isinstance(type_filling_input, int):
        allowed = set(TYPE_FILLING_MAP.values())
        if type_filling_input not in allowed:
            return None, "Invalid integer type_filling"
        return type_filling_input, None
    else:
        return (
            None,
            "type_filling must be a string (FOK, IOC, RETURN) or integer constant",
        )
