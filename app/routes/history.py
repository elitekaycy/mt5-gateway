import logging
from datetime import datetime

from flasgger import swag_from
from flask import Blueprint, jsonify, request

from deal_window import DealWindowError, parse_deal_window
from decorators import require_mt5_connection
from errors import (
    internal_error_response,
    mt5_connection_error_response,
    not_found_response,
    validation_error_response,
)
from lib import get_deal_from_ticket, get_order_from_ticket
from mt5_connection import mt5
from request_limits import validate_date_range, validate_tick_flags

history_bp = Blueprint("history", __name__)
logger = logging.getLogger(__name__)


@history_bp.route("/get_deal_from_ticket", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "ticket",
                "in": "query",
                "type": "integer",
                "required": True,
                "description": "Position ticket number to retrieve deal information.",
            }
        ],
        "responses": {
            200: {
                "description": "Deal information retrieved successfully.",
                "schema": {"$ref": "#/definitions/DealInfo"},
            },
            400: {"description": "Invalid ticket format."},
            404: {"description": "Failed to get deal information."},
            500: {"description": "Internal server error."},
        },
    }
)
def get_deal_from_ticket_endpoint():
    """
    Get Deal Information from Position Ticket
    ---
    description: Retrieve deal information associated with a specific position ticket number.
    """
    try:
        ticket = request.args.get("ticket")
        if not ticket:
            return validation_error_response("Ticket parameter is required")

        try:
            ticket = int(ticket)
        except ValueError:
            return validation_error_response("Invalid ticket format")

        deal = get_deal_from_ticket(ticket)
        if deal is None:
            return not_found_response("deal", ticket)

        return jsonify(deal)

    except Exception as e:
        return internal_error_response("get_deal_from_ticket", e)


@history_bp.route("/get_order_from_ticket", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "ticket",
                "in": "query",
                "type": "integer",
                "required": True,
                "description": "Ticket number to retrieve order information.",
            }
        ],
        "responses": {
            200: {
                "description": "Order information retrieved successfully.",
                "schema": {"$ref": "#/definitions/HistoryOrder"},
            },
            400: {"description": "Invalid ticket format."},
            404: {"description": "Failed to get order information."},
            500: {"description": "Internal server error."},
        },
    }
)
def get_order_from_ticket_endpoint():
    """
    Get Order Information from Ticket
    ---
    description: Retrieve order information associated with a specific ticket number.
    """
    try:
        ticket = request.args.get("ticket")
        if not ticket:
            return validation_error_response("Ticket parameter is required")

        try:
            ticket = int(ticket)
        except ValueError:
            return validation_error_response("Invalid ticket format")

        order = get_order_from_ticket(ticket)
        if order is None:
            return not_found_response("order", ticket)

        return jsonify(order)

    except Exception as e:
        return internal_error_response("get_order_from_ticket", e)


@history_bp.route("/history_deals_get", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "from_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
                "description": "Start date in ISO format.",
            },
            {
                "name": "to_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
                "description": "End date in ISO format.",
            },
            {
                "name": "position",
                "in": "query",
                "type": "integer",
                "required": False,
                "description": "Position number to filter deals. Omit for every deal in the range.",
            },
        ],
        "responses": {
            200: {
                "description": "Deals history retrieved successfully.",
                "schema": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/DealInfo"},
                },
            },
            400: {"description": "Invalid parameter format or missing parameters."},
            404: {"description": "Failed to get deals history."},
            500: {"description": "Internal server error."},
        },
    }
)
def history_deals_get_endpoint():
    """
    Get Deals History
    ---
    description: Retrieve historical deals within a date range, optionally filtered to one position.
    """
    try:
        try:
            from_timestamp, to_timestamp, position = parse_deal_window(request.args)
        except DealWindowError as e:
            return validation_error_response(str(e))

        if position is not None:
            deals = mt5.history_deals_get(
                from_timestamp, to_timestamp, position=position
            )
        else:
            deals = mt5.history_deals_get(from_timestamp, to_timestamp)

        if deals is None:
            return mt5_connection_error_response(
                "Get deals history", mt5.last_call_error()
            )

        deals_list = [deal._asdict() for deal in deals]
        return jsonify(deals_list)

    except Exception as e:
        return internal_error_response("history_deals_get", e)


@history_bp.route("/history_orders_get", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "ticket",
                "in": "query",
                "type": "integer",
                "required": True,
                "description": "Ticket number to retrieve orders history.",
            }
        ],
        "responses": {
            200: {
                "description": "Orders history retrieved successfully.",
                "schema": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/HistoryOrder"},
                },
            },
            400: {"description": "Invalid ticket format or missing parameter."},
            404: {"description": "Failed to get orders history."},
            500: {"description": "Internal server error."},
        },
    }
)
def history_orders_get_endpoint():
    """
    Get Orders History
    ---
    description: Retrieve historical orders associated with a specific ticket number.
    """
    try:
        ticket = request.args.get("ticket")
        if not ticket:
            return validation_error_response("Ticket parameter is required")

        try:
            ticket = int(ticket)
        except ValueError:
            return validation_error_response("Invalid ticket format")

        orders = mt5.history_orders_get(ticket=ticket)
        if orders is None:
            return mt5_connection_error_response(
                "Get orders history", mt5.last_call_error()
            )

        orders_list = [order._asdict() for order in orders]
        return jsonify(orders_list)

    except Exception as e:
        return internal_error_response("history_orders_get", e)


@history_bp.route("/history_deals_range", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "from_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
                "description": "Start date in ISO format.",
            },
            {
                "name": "to_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
                "description": "End date in ISO format.",
            },
            {
                "name": "magic",
                "in": "query",
                "type": "integer",
                "required": False,
                "description": "Optional magic number to filter deals.",
            },
        ],
        "responses": {
            200: {
                "description": "Deals retrieved.",
                "schema": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/DealInfo"},
                },
            },
            400: {"description": "Invalid parameters."},
            500: {"description": "Internal error."},
        },
    }
)
def history_deals_range_endpoint():
    """
    Bulk Deals History (date range, optional magic filter)
    ---
    description: Retrieve historical deals within a date range without requiring a position ticket.
    """
    try:
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        magic_raw = request.args.get("magic")

        if not from_date or not to_date:
            return validation_error_response(
                "from_date and to_date parameters are required"
            )

        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        except ValueError as e:
            return validation_error_response(f"Invalid date format: {str(e)}")

        if from_dt >= to_dt:
            return validation_error_response("from_date must be before to_date")
        try:
            validate_date_range(from_dt, to_dt)
        except ValueError as error:
            return validation_error_response(str(error))

        magic = None
        if magic_raw is not None:
            try:
                magic = int(magic_raw)
            except ValueError:
                return validation_error_response("Invalid magic format")

        from_ts = int(from_dt.timestamp())
        to_ts = int(to_dt.timestamp())
        deals = mt5.history_deals_get(from_ts, to_ts)

        if deals is None:
            return mt5_connection_error_response(
                "Get deals history range", mt5.last_call_error()
            )

        deals_list = [d._asdict() for d in deals]
        if magic is not None:
            deals_list = [d for d in deals_list if d.get("magic") == magic]

        return jsonify(deals_list)

    except Exception as e:
        return internal_error_response("history_deals_range", e)


@history_bp.route("/copy_ticks_range", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["History"],
        "parameters": [
            {
                "name": "symbol",
                "in": "query",
                "type": "string",
                "required": True,
                "description": "Symbol name (e.g. XAUUSDm).",
            },
            {
                "name": "from_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
            },
            {
                "name": "to_date",
                "in": "query",
                "type": "string",
                "required": True,
                "format": "date-time",
            },
            {
                "name": "flags",
                "in": "query",
                "type": "integer",
                "required": False,
                "description": "MT5 COPY_TICKS flag (default = ALL).",
            },
        ],
        "responses": {
            200: {
                "description": "Ticks retrieved.",
                "schema": {"type": "array", "items": {"type": "object"}},
            },
            400: {"description": "Invalid parameters."},
            500: {"description": "Internal error."},
        },
    }
)
def copy_ticks_range_endpoint():
    """
    Tick History (date range)
    ---
    description: Retrieve raw tick data for a symbol within a date range.
    """
    try:
        symbol = request.args.get("symbol")
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        flags_raw = request.args.get("flags")

        if not symbol or not from_date or not to_date:
            return validation_error_response(
                "symbol, from_date, to_date parameters are required"
            )

        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        except ValueError as e:
            return validation_error_response(f"Invalid date format: {str(e)}")

        if from_dt >= to_dt:
            return validation_error_response("from_date must be before to_date")
        try:
            validate_date_range(from_dt, to_dt)
        except ValueError as error:
            return validation_error_response(str(error))

        flags = mt5.COPY_TICKS_ALL
        if flags_raw is not None:
            try:
                flags = validate_tick_flags(flags_raw)
            except ValueError:
                return validation_error_response("Invalid flags format")

        ticks = mt5.copy_ticks_range(symbol, from_dt, to_dt, flags)
        if ticks is None:
            return mt5_connection_error_response(
                "Copy ticks range", mt5.last_call_error()
            )

        ticks_list = []
        for t in ticks:
            row = {
                "time": int(t["time"]),
                "bid": float(t["bid"]),
                "ask": float(t["ask"]),
            }
            names = t.dtype.names if hasattr(t, "dtype") else ()
            if "time_msc" in names:
                row["time_msc"] = int(t["time_msc"])
            if "last" in names:
                row["last"] = float(t["last"])
            if "volume" in names:
                row["volume"] = int(t["volume"])
            if "flags" in names:
                row["flags"] = int(t["flags"])
            ticks_list.append(row)

        return jsonify(ticks_list)

    except Exception as e:
        return internal_error_response("copy_ticks_range", e)
