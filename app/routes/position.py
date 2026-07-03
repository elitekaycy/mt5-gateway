import logging
import math

from decorators import require_mt5_connection
from errors import (
    internal_error_response,
    mt5_error_response,
    unknown_outcome_response,
    validation_error_response,
)
from flasgger import swag_from
from flask import Blueprint, jsonify, request
from lib import (
    close_all_positions,
    close_position,
    get_positions,
    get_symbol_filling_mode,
    validate_sl_tp,
    validate_symbol,
    validate_volume,
)
from mt5_connection import mt5
from order_requests import OrderRequestError, build_sltp_request
from retcodes import classify_retcode

position_bp = Blueprint("position", __name__)
logger = logging.getLogger(__name__)


@position_bp.route("/close_position", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/ClosePositionRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Position closed successfully.",
                "schema": {"$ref": "#/definitions/ClosePositionResponse"},
            },
            400: {"description": "Bad request or failed to close position."},
            500: {"description": "Internal server error."},
        },
    }
)
def close_position_endpoint():
    """
    Close a Specific Position
    ---
    description: Close a specific trading position based on the provided position data.
    """
    try:
        data = request.get_json()
        if not data or "position" not in data:
            return validation_error_response("Position data is required")

        result = close_position(data["position"])
        if result is None:
            return validation_error_response("Failed to close position")

        info = classify_retcode(result.retcode)
        if not info.is_success:
            return mt5_error_response("Close position", result)

        result_data = result._asdict()
        partial = info.name == "DONE_PARTIAL"
        result_data["partial"] = partial
        if partial:
            original_volume = float(data["position"].get("volume", result.volume))
            result_data["remaining_volume"] = max(
                0.0, original_volume - float(result.volume)
            )
        return jsonify(
            {"message": "Position closed successfully", "result": result_data}
        )

    except Exception as e:
        return internal_error_response("close_position", e)


@position_bp.route("/position_close_partial", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "summary": "Partially close position",
        "description": "Close a portion of an open position by specifying the volume to close. The remaining volume stays open.",
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/ClosePositionPartialRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Position partially closed successfully.",
                "schema": {"$ref": "#/definitions/ClosePositionPartialResponse"},
            },
            400: {"description": "Validation error or failed to close position."},
            503: {"description": "MT5 unavailable"},
        },
    }
)
def close_position_partial_endpoint():
    """
    Partially Close Position
    ---
    description: Close a specific volume of an open position, leaving the remainder open.
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("Position data is required")

        required_fields = ["ticket", "volume"]
        if not all(field in data for field in required_fields):
            return validation_error_response(
                "Missing required fields", {"required": required_fields}
            )

        try:
            ticket = int(data["ticket"])
            volume = float(data["volume"])
        except (TypeError, ValueError):
            return validation_error_response("Ticket and volume must be numeric")
        deviation = data.get("deviation", 20)
        comment = data.get("comment", "Partial close")

        if not math.isfinite(volume) or volume <= 0:
            return validation_error_response("Volume must be positive")

        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return validation_error_response(f"Position {ticket} not found")

        position = positions[0]
        symbol = position.symbol
        position_type = position.type

        if "symbol" in data and data["symbol"] != symbol:
            return validation_error_response(f"Symbol does not match position {ticket}")
        if "type" in data and int(data["type"]) != position_type:
            return validation_error_response(f"Type does not match position {ticket}")
        if not validate_symbol(symbol):
            return validation_error_response(
                f"Symbol not found or not selectable: {symbol}"
            )
        is_valid, error_msg = validate_volume(symbol, volume)
        if not is_valid:
            return validation_error_response(error_msg)

        if volume >= position.volume:
            return validation_error_response(
                f"Volume to close ({volume}) must be less than position volume ({position.volume}). Use /close_position to close entire position."
            )

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return validation_error_response(f"Failed to get tick for {symbol}")

        order_type_dict = {0: mt5.ORDER_TYPE_SELL, 1: mt5.ORDER_TYPE_BUY}

        if position_type not in order_type_dict:
            return validation_error_response(
                f"Invalid position type: {position_type}. Must be 0 (BUY) or 1 (SELL)"
            )

        order_type = order_type_dict[position_type]

        price = tick.bid if position_type == 0 else tick.ask

        type_filling = get_symbol_filling_mode(symbol)

        request_data = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": position.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        result = mt5.order_send(request_data)

        if result is None:
            logger.error(
                f"order_send returned None for partial close of position {ticket}"
            )
            return unknown_outcome_response(
                "Partial close position", mt5.last_order_error()
            )

        if not classify_retcode(result.retcode).is_success:
            logger.error(
                f"Failed to partially close position {ticket}: retcode={result.retcode}, comment={result.comment}"
            )
            return mt5_error_response("Partial close position", result)

        info = classify_retcode(result.retcode)
        filled_volume = float(getattr(result, "volume", volume))
        remaining_volume = max(0.0, float(position.volume) - filled_volume)
        logger.info(
            f"Position {ticket} partially closed: {filled_volume} lots at {price}"
        )

        return jsonify(
            {
                "message": "Position partially closed successfully",
                "result": result._asdict(),
                "partial": info.name == "DONE_PARTIAL",
                "remaining_volume": remaining_volume,
            }
        )

    except Exception as e:
        return internal_error_response("close_position_partial", e)


@position_bp.route("/close_all_positions", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": False,
                "schema": {"$ref": "#/definitions/CloseAllPositionsRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Closed positions successfully.",
                "schema": {"$ref": "#/definitions/CloseAllPositionsResponse"},
            },
            400: {"description": "Bad request or no positions were closed."},
            500: {"description": "Internal server error."},
        },
    }
)
def close_all_positions_endpoint():
    """
    Close All Positions
    ---
    description: Close all open trading positions based on optional filters like order type and magic number.
    """
    try:
        data = request.get_json() or {}
        order_type = data.get("order_type", "all")
        magic = data.get("magic")

        outcome = close_all_positions(order_type, magic)
        if not outcome["closed"] and not outcome["failed"]:
            return jsonify({"message": "No positions were closed"}), 200

        payload = {
            "message": (
                f"Closed {len(outcome['closed'])} positions; "
                f"{len(outcome['failed'])} failed"
            ),
            **outcome,
        }
        return jsonify(payload), 207 if outcome["failed"] else 200

    except Exception as e:
        return internal_error_response("close_all_positions", e)


@position_bp.route("/modify_sl_tp", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/ModifySLTPRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "SL/TP modified successfully.",
                "schema": {"$ref": "#/definitions/ModifySLTPResponse"},
            },
            400: {"description": "Bad request or failed to modify SL/TP."},
            500: {"description": "Internal server error."},
        },
    }
)
def modify_sl_tp_endpoint():
    """
    Modify Stop Loss and Take Profit
    ---
    description: Modify the Stop Loss (SL) and Take Profit (TP) levels for a specific position.
    """
    try:
        data = request.get_json()
        if not data or "position" not in data:
            return validation_error_response("Position data is required")

        try:
            position = int(data["position"])
        except (TypeError, ValueError):
            return validation_error_response("Position must be an integer")
        positions = mt5.positions_get(ticket=position)
        if not positions:
            logger.error(f"Position {position} not found for SL/TP modify")
            return validation_error_response(f"Position {position} not found")

        try:
            request_data = build_sltp_request(data, positions[0], mt5.TRADE_ACTION_SLTP)
        except OrderRequestError as error:
            return validation_error_response(str(error))

        current = positions[0]
        sl = request_data["sl"] if request_data["sl"] > 0 else None
        tp = request_data["tp"] if request_data["tp"] > 0 else None
        is_valid, error_msg = validate_sl_tp(
            current.type, current.price_current, sl, tp
        )
        if not is_valid:
            return validation_error_response(error_msg)

        result = mt5.order_send(request_data)

        if result is None:
            last_err = mt5.last_order_error()
            logger.error(
                f"order_send returned None for modify SL/TP position {position}, last_error={last_err}"
            )
            return unknown_outcome_response("Modify SL/TP", last_err)

        if not classify_retcode(result.retcode).is_success:
            return mt5_error_response("Modify SL/TP", result)

        return jsonify(
            {"message": "SL/TP modified successfully", "result": result._asdict()}
        )

    except Exception as e:
        return internal_error_response("modify_sl_tp", e)


@position_bp.route("/get_positions", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "parameters": [
            {
                "name": "magic",
                "in": "query",
                "type": "integer",
                "required": False,
                "description": "Magic number to filter positions.",
            }
        ],
        "responses": {
            200: {
                "description": "Positions retrieved successfully.",
                "schema": {"$ref": "#/definitions/PositionsResponse"},
            },
            400: {"description": "Bad request or failed to retrieve positions."},
            500: {"description": "Internal server error."},
        },
    }
)
def get_positions_endpoint():
    """
    Get Open Positions
    ---
    description: Retrieve all open trading positions, optionally filtered by magic number.
    """
    try:
        magic = request.args.get("magic", type=int)

        positions_df = get_positions(magic)

        if positions_df is None:
            return internal_error_response(
                "get_positions", Exception("Failed to retrieve positions")
            )

        if positions_df.empty:
            return jsonify([]), 200

        return jsonify(positions_df.to_dict(orient="records")), 200

    except Exception as e:
        return internal_error_response("get_positions", e)


@position_bp.route("/positions_total", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Position"],
        "responses": {
            200: {
                "description": "Total number of open positions retrieved successfully.",
                "schema": {"$ref": "#/definitions/PositionsTotalResponse"},
            },
            400: {"description": "Failed to get positions total."},
            500: {"description": "Internal server error."},
        },
    }
)
def positions_total_endpoint():
    """
    Get Total Open Positions
    ---
    description: Retrieve the total number of open trading positions.
    """
    try:
        total = mt5.positions_total()
        if total is None:
            return validation_error_response("Failed to get positions total")

        return jsonify({"total": total})

    except Exception as e:
        return internal_error_response("positions_total", e)
