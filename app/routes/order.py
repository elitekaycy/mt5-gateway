import json
import logging
import os

from mt5_connection import mt5
from constants import ORDER_TYPE_TO_STRING, TRADE_ACTION_DEAL, TRADE_ACTION_PENDING
from decorators import require_mt5_connection
from errors import (
    internal_error_response,
    mt5_error_response,
    unknown_outcome_response,
    validation_error_response,
)
from flasgger import swag_from
from flask import Blueprint, g, jsonify, request
from idempotency import (
    Decision,
    IdempotencyStore,
    magic_from_key,
    request_fingerprint,
)
from lib import (
    validate_pending_price,
    validate_sl_tp,
    validate_symbol,
    validate_type_filling,
    validate_volume,
)
from order_time import apply_expiration
from retcodes import classify_retcode, success_state

order_bp = Blueprint("order", __name__)
logger = logging.getLogger(__name__)
idempotency_store = IdempotencyStore(
    ttl_seconds=float(os.getenv("MT5_IDEMPOTENCY_TTL", "3600"))
)


@order_bp.route("/order", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Send market or pending order",
        "description": "Execute a market order immediately or place a pending order. Market orders (BUY/SELL) execute at current price. Pending orders (BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP) are placed and triggered when price conditions are met.",
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/OrderRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Order executed or placed successfully.",
                "schema": {"$ref": "#/definitions/OrderResponse"},
            },
            400: {
                "description": "Validation error or order rejected by broker.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            503: {
                "description": "MT5 connection unavailable",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def send_market_order_endpoint():
    """
    Send Order
    ---
    description: Execute a market order or place a pending order for a specified symbol.
    """
    idempotency_key = None
    fingerprint = None
    reservation_owned = False
    reservation_completed = False
    try:
        request_id = getattr(g, "request_id", "unknown")
        data = request.get_json()

        logger.info(f"[{request_id}] Received order request: {json.dumps(data)}")

        if not data:
            return validation_error_response("Order data is required")

        body_key = data.get("client_order_id")
        header_key = request.headers.get("Idempotency-Key")
        if body_key and header_key and body_key != header_key:
            return validation_error_response(
                "client_order_id and Idempotency-Key must match"
            )
        idempotency_key = body_key or header_key
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str):
                return validation_error_response("client_order_id must be a string")
            idempotency_key = idempotency_key.strip()
            if not 1 <= len(idempotency_key) <= 128:
                return validation_error_response(
                    "client_order_id must contain 1 to 128 characters"
                )

            fingerprint = request_fingerprint(data)
            decision, stored = idempotency_store.begin(
                idempotency_key, fingerprint
            )
            if decision is Decision.REPLAY:
                response = jsonify(stored.payload)
                response.headers["Idempotent-Replayed"] = "true"
                return response, stored.status_code
            if decision is Decision.CONFLICT:
                return jsonify(
                    {
                        "error": "Idempotency key was already used with different parameters",
                        "error_type": "idempotency_conflict",
                    }
                ), 409
            if decision is Decision.IN_PROGRESS:
                return jsonify(
                    {
                        "error": "An order with this idempotency key is in progress",
                        "error_type": "idempotency_in_progress",
                    }
                ), 409
            reservation_owned = True

        required_fields = ["symbol", "volume", "type"]
        if not all(field in data for field in required_fields):
            return validation_error_response(
                "Missing required fields", {"required": required_fields}
            )

        if not validate_symbol(data["symbol"]):
            return validation_error_response(
                f"Symbol not found or not selectable: {data['symbol']}"
            )

        ORDER_TYPE_MAP = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
            "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
            "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
        }

        order_type_str = (
            data["type"].upper() if isinstance(data["type"], str) else str(data["type"])
        )
        if order_type_str not in ORDER_TYPE_MAP:
            return validation_error_response(f"Invalid order type: {data['type']}")

        order_type = ORDER_TYPE_MAP[order_type_str]

        volume = float(data["volume"])
        if volume <= 0:
            return validation_error_response("Volume must be positive")

        is_valid, error_msg = validate_volume(data["symbol"], volume)
        if not is_valid:
            return validation_error_response(error_msg)

        if order_type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            action = TRADE_ACTION_DEAL

            tick = mt5.symbol_info_tick(data["symbol"])
            if tick is None:
                logger.error(f"[{request_id}] Failed to get tick for {data['symbol']}")
                return validation_error_response(
                    f"Failed to get symbol price for {data['symbol']}"
                )

            price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

            logger.info(
                f"[{request_id}] Market order - fetched price from MT5: type={order_type_str}, bid={tick.bid}, ask={tick.ask}, using_price={price}"
            )

            if "price" in data:
                logger.warning(
                    f"[{request_id}] Price ignored for market orders, using current tick"
                )

        elif order_type in [
            mt5.ORDER_TYPE_BUY_LIMIT,
            mt5.ORDER_TYPE_SELL_LIMIT,
            mt5.ORDER_TYPE_BUY_STOP,
            mt5.ORDER_TYPE_SELL_STOP,
        ]:
            action = TRADE_ACTION_PENDING

            if "price" not in data:
                return validation_error_response("Price required for pending orders")

            price = float(data["price"])
            if price <= 0:
                return validation_error_response("Price must be positive")

            is_valid, error_msg = validate_pending_price(
                order_type, data["symbol"], price
            )
            if not is_valid:
                return validation_error_response(error_msg)
        else:
            return validation_error_response("Invalid order type")

        sl = data.get("sl")
        tp = data.get("tp")

        if sl is not None:
            sl = float(sl)
        if tp is not None:
            tp = float(tp)

        logger.info(
            f"[{request_id}] SL/TP from request: sl={sl}, tp={tp}, entry_price={price}"
        )

        if sl is not None or tp is not None:
            is_valid, error_msg = validate_sl_tp(order_type, price, sl, tp)
            if not is_valid:
                logger.error(
                    f"[{request_id}] SL/TP validation failed: {error_msg} (order_type={order_type_str}, price={price}, sl={sl}, tp={tp})"
                )
                return validation_error_response(error_msg)
            logger.info(f"[{request_id}] SL/TP validation passed")

        type_filling = mt5.ORDER_FILLING_IOC
        if "type_filling" in data:
            type_filling, error_msg = validate_type_filling(data["type_filling"])
            if error_msg:
                return validation_error_response(error_msg)

        request_data = {
            "action": action,
            "symbol": data["symbol"],
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": data.get("deviation", 20),
            "magic": data.get(
                "magic",
                magic_from_key(idempotency_key) if idempotency_key else 0,
            ),
            "comment": data.get("comment", ""),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        apply_expiration(request_data, data)

        if sl is not None:
            request_data["sl"] = sl
        if tp is not None:
            request_data["tp"] = tp

        logger.info(
            f"[{request_id}] Sending order to MT5: {json.dumps({k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in request_data.items()})}"
        )

        result = mt5.order_send(request_data)

        if result is None:
            logger.error(
                f"[{request_id}] order_send returned None for {order_type_str} {data['symbol']}"
            )
            response, status_code = unknown_outcome_response(
                "Send order", mt5.last_order_error()
            )
            if reservation_owned:
                idempotency_store.complete(
                    idempotency_key,
                    fingerprint,
                    response.get_json(),
                    status_code,
                )
                reservation_completed = True
            return response, status_code

        retcode_info = classify_retcode(result.retcode)
        if not retcode_info.is_success:
            logger.error(
                f"[{request_id}] MT5 rejected order: retcode={result.retcode}, comment={result.comment}"
            )
            response, status_code = mt5_error_response("Send order", result)
            if reservation_owned and retcode_info.is_ambiguous:
                idempotency_store.complete(
                    idempotency_key,
                    fingerprint,
                    response.get_json(),
                    status_code,
                )
                reservation_completed = True
            return response, status_code

        state = success_state(result.retcode)
        partial_fill = state == "partially_executed"
        if partial_fill:
            logger.warning(
                f"[{request_id}] Partial fill: requested={volume}, filled={result.volume}"
            )

        action_str = "executed" if action == TRADE_ACTION_DEAL else "placed"
        logger.info(
            f"[{request_id}] Order {action_str} successfully: {order_type_str}, symbol={data['symbol']}, volume={volume}, price={result.price}, order={result.order}, deal={result.deal}"
        )

        result_dict = result._asdict()
        payload = {
            "message": f"Order {action_str} successfully",
            "state": state,
            "result": result_dict,
            "sl_confirmed": result_dict.get("sl"),
            "tp_confirmed": result_dict.get("tp"),
            "partial_fill": partial_fill,
        }
        if idempotency_key:
            payload["client_order_id"] = idempotency_key
        if reservation_owned:
            idempotency_store.complete(
                idempotency_key, fingerprint, payload, 200
            )
            reservation_completed = True
        return jsonify(payload)

    except Exception as e:
        return internal_error_response("send_order", e)
    finally:
        if reservation_owned and not reservation_completed:
            idempotency_store.abandon(idempotency_key, fingerprint)


@order_bp.route("/order_check", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Validate order without executing",
        "description": "Check if an order would be accepted and calculate margin requirements without actually placing it. Useful for pre-trade validation and risk management.",
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/OrderCheckRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Order validation result (valid=true means order would be accepted).",
                "schema": {"$ref": "#/definitions/OrderCheckResponse"},
            },
            400: {
                "description": "Validation failed - order parameters invalid or would be rejected.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def order_check_endpoint():
    """
    Check Order Validity
    ---
    description: Validate an order without executing it to check margin requirements and feasibility.
    """
    try:
        request_id = getattr(g, "request_id", "unknown")
        data = request.get_json()

        logger.info(f"[{request_id}] Received order_check request: {json.dumps(data)}")

        if not data:
            return validation_error_response("Order data is required")

        required_fields = ["symbol", "volume", "type"]
        if not all(field in data for field in required_fields):
            return validation_error_response(
                "Missing required fields", {"required": required_fields}
            )

        if not validate_symbol(data["symbol"]):
            return validation_error_response(
                f"Symbol not found or not selectable: {data['symbol']}"
            )

        ORDER_TYPE_MAP = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
            "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
            "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
        }

        order_type_str = (
            data["type"].upper() if isinstance(data["type"], str) else str(data["type"])
        )
        if order_type_str not in ORDER_TYPE_MAP:
            return validation_error_response(f"Invalid order type: {data['type']}")

        order_type = ORDER_TYPE_MAP[order_type_str]

        volume = float(data["volume"])
        if volume <= 0:
            return validation_error_response("Volume must be positive")

        is_valid, error_msg = validate_volume(data["symbol"], volume)
        if not is_valid:
            return validation_error_response(error_msg)

        if order_type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            action = TRADE_ACTION_DEAL
            tick = mt5.symbol_info_tick(data["symbol"])
            if tick is None:
                return validation_error_response(
                    f"Failed to get symbol price for {data['symbol']}"
                )

            price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

            if "price" in data:
                logger.warning("Price ignored for market orders, using current tick")

        elif order_type in [
            mt5.ORDER_TYPE_BUY_LIMIT,
            mt5.ORDER_TYPE_SELL_LIMIT,
            mt5.ORDER_TYPE_BUY_STOP,
            mt5.ORDER_TYPE_SELL_STOP,
        ]:
            action = TRADE_ACTION_PENDING

            if "price" not in data:
                return validation_error_response("Price required for pending orders")

            price = float(data["price"])
            if price <= 0:
                return validation_error_response("Price must be positive")

            is_valid, error_msg = validate_pending_price(
                order_type, data["symbol"], price
            )
            if not is_valid:
                return validation_error_response(error_msg)
        else:
            return validation_error_response("Invalid order type")

        sl = data.get("sl")
        tp = data.get("tp")

        if sl is not None:
            sl = float(sl)
        if tp is not None:
            tp = float(tp)

        logger.info(
            f"[{request_id}] SL/TP from request: sl={sl}, tp={tp}, entry_price={price}"
        )

        if sl is not None or tp is not None:
            is_valid, error_msg = validate_sl_tp(order_type, price, sl, tp)
            if not is_valid:
                logger.error(
                    f"[{request_id}] SL/TP validation failed: {error_msg} (order_type={order_type_str}, price={price}, sl={sl}, tp={tp})"
                )
                return validation_error_response(error_msg)
            logger.info(f"[{request_id}] SL/TP validation passed")

        type_filling = mt5.ORDER_FILLING_IOC
        if "type_filling" in data:
            type_filling, error_msg = validate_type_filling(data["type_filling"])
            if error_msg:
                return validation_error_response(error_msg)

        request_data = {
            "action": action,
            "symbol": data["symbol"],
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": data.get("deviation", 20),
            "magic": data.get("magic", 0),
            "comment": data.get("comment", ""),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        apply_expiration(request_data, data)

        if sl is not None:
            request_data["sl"] = sl
        if tp is not None:
            request_data["tp"] = tp

        result = mt5.order_check(request_data)
        if result is None:
            return validation_error_response(
                "Order check failed - MT5 returned None"
            ), 400

        if result.retcode != mt5.TRADE_RETCODE_DONE and result.retcode != 0:
            return jsonify(
                {
                    "valid": False,
                    "retcode": result.retcode,
                    "comment": result.comment,
                    "margin": result.margin if hasattr(result, "margin") else None,
                    "margin_free": result.margin_free
                    if hasattr(result, "margin_free")
                    else None,
                }
            ), 400

        return jsonify({"valid": True, **result._asdict()})

    except Exception as e:
        return internal_error_response("order_check", e)


@order_bp.route("/order_calc_margin", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Calculate required margin",
        "description": "Calculate how much margin (collateral) would be required to open a position. Does not place any order.",
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/MarginCalculationRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Margin calculated successfully.",
                "schema": {"$ref": "#/definitions/MarginCalculationResponse"},
            },
            400: {
                "description": "Invalid parameters or margin calculation unavailable for this symbol.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def order_calc_margin_endpoint():
    """
    Calculate Order Margin
    ---
    description: Calculate the required margin for an order without placing it.
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("Order data is required")

        required_fields = ["symbol", "volume", "type", "price"]
        if not all(field in data for field in required_fields):
            return validation_error_response(
                "Missing required fields", {"required": required_fields}
            )

        if not validate_symbol(data["symbol"]):
            return validation_error_response(
                f"Symbol not found or not selectable: {data['symbol']}"
            )

        ORDER_TYPE_MAP = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
            "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
            "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
        }

        order_type_str = (
            data["type"].upper() if isinstance(data["type"], str) else str(data["type"])
        )
        if order_type_str not in ORDER_TYPE_MAP:
            return validation_error_response(f"Invalid order type: {data['type']}")

        order_type = ORDER_TYPE_MAP[order_type_str]

        volume = float(data["volume"])
        if volume <= 0:
            return validation_error_response("Volume must be positive")

        price = float(data["price"])
        if price <= 0:
            return validation_error_response("Price must be positive")

        is_valid, error_msg = validate_volume(data["symbol"], volume)
        if not is_valid:
            return validation_error_response(error_msg)

        if order_type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            action = TRADE_ACTION_DEAL
        else:
            action = TRADE_ACTION_PENDING

        margin = mt5.order_calc_margin(action, data["symbol"], volume, price)

        if margin is None:
            logger.warning(
                f"Margin calculation returned None for {data['symbol']}, volume={volume}, price={price}"
            )
            return validation_error_response(
                "Margin calculation unavailable",
                {
                    "reason": "Symbol may not support this calculation or parameters are invalid"
                },
            ), 400

        if margin < 0:
            logger.warning(f"Negative margin calculated for {data['symbol']}: {margin}")
            return validation_error_response("Invalid margin calculation result"), 400

        return jsonify({"margin": margin})

    except Exception as e:
        return internal_error_response("order_calc_margin", e)


@order_bp.route("/order_calc_profit", methods=["POST"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Calculate hypothetical profit",
        "description": "Calculate profit/loss for a hypothetical position between two prices. Does NOT include swap or commission - only price difference profit.",
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/ProfitCalculationRequest"},
            }
        ],
        "responses": {
            200: {
                "description": "Profit calculated successfully.",
                "schema": {"$ref": "#/definitions/ProfitCalculationResponse"},
            },
            400: {
                "description": "Invalid parameters or profit calculation unavailable for this symbol.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def order_calc_profit_endpoint():
    """
    Calculate Order Profit
    ---
    description: Calculate the hypothetical profit for closing a position at a given price.
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("Order data is required")

        required_fields = ["symbol", "volume", "type", "price_open", "price_close"]
        if not all(field in data for field in required_fields):
            return validation_error_response(
                "Missing required fields", {"required": required_fields}
            )

        if not validate_symbol(data["symbol"]):
            return validation_error_response(
                f"Symbol not found or not selectable: {data['symbol']}"
            )

        ORDER_TYPE_MAP = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
        }

        order_type_str = (
            data["type"].upper() if isinstance(data["type"], str) else str(data["type"])
        )
        if order_type_str not in ORDER_TYPE_MAP:
            return validation_error_response(
                f"Invalid order type: {data['type']}. Must be 'BUY' or 'SELL'"
            )

        order_type = ORDER_TYPE_MAP[order_type_str]

        volume = float(data["volume"])
        if volume <= 0:
            return validation_error_response("Volume must be positive")

        price_open = float(data["price_open"])
        if price_open <= 0:
            return validation_error_response("Opening price must be positive")

        price_close = float(data["price_close"])
        if price_close <= 0:
            return validation_error_response("Closing price must be positive")

        is_valid, error_msg = validate_volume(data["symbol"], volume)
        if not is_valid:
            return validation_error_response(error_msg)

        action = data.get("action", "DEAL").upper()
        if action == "DEAL":
            mt5_action = TRADE_ACTION_DEAL
        elif action == "PENDING":
            mt5_action = TRADE_ACTION_PENDING
        else:
            mt5_action = TRADE_ACTION_DEAL

        profit = mt5.order_calc_profit(
            mt5_action, data["symbol"], volume, price_open, price_close
        )

        if profit is None:
            logger.warning(
                f"Profit calculation returned None for {data['symbol']}, volume={volume}, price_open={price_open}, price_close={price_close}"
            )
            return validation_error_response(
                "Profit calculation unavailable",
                {"reason": "Symbol may not support this calculation"},
            ), 400

        logger.info(
            f"Profit calculated: symbol={data['symbol']}, volume={volume}, price_open={price_open}, price_close={price_close}, profit={profit}"
        )

        return jsonify({"profit": profit})

    except Exception as e:
        return internal_error_response("order_calc_profit", e)


@order_bp.route("/orders", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Get pending orders",
        "description": "Retrieve all pending orders (LIMIT and STOP orders that have not been triggered yet). Does NOT include active positions - use /positions for that.",
        "parameters": [
            {
                "name": "symbol",
                "in": "query",
                "type": "string",
                "required": False,
                "description": "Filter pending orders by symbol (e.g., EURUSD)",
                "example": "EURUSD",
            },
            {
                "name": "ticket",
                "in": "query",
                "type": "integer",
                "required": False,
                "description": "Get specific pending order by ticket number",
                "example": 123456789,
            },
        ],
        "responses": {
            200: {
                "description": "Pending orders retrieved successfully. Returns empty array if no pending orders.",
                "schema": {"$ref": "#/definitions/PendingOrdersResponse"},
            },
            400: {
                "description": "Invalid parameters (e.g., invalid symbol or ticket format).",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            503: {
                "description": "MT5 unavailable or failed to retrieve orders.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def get_pending_orders():
    """
    Get Pending Orders
    ---
    description: Retrieve all pending orders, optionally filtered by symbol or ticket.
    """
    try:
        symbol = request.args.get("symbol")
        ticket = request.args.get("ticket")

        if ticket:
            try:
                ticket_int = int(ticket)
                orders = mt5.orders_get(ticket=ticket_int)
            except ValueError:
                return validation_error_response("Ticket must be an integer")
        elif symbol:
            if not validate_symbol(symbol):
                return validation_error_response(f"Invalid symbol: {symbol}")
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()

        if orders is None:
            logger.error(
                "Failed to retrieve pending orders - mt5.orders_get() returned None"
            )
            return jsonify(
                {
                    "error": "Failed to retrieve pending orders",
                    "error_type": "connection_error",
                }
            ), 503

        orders_list = []
        for order in orders:
            order_dict = order._asdict()
            order_dict["type_str"] = ORDER_TYPE_TO_STRING.get(
                order.type, f"UNKNOWN_{order.type}"
            )
            orders_list.append(order_dict)

        logger.info(
            f"Retrieved {len(orders_list)} pending orders",
            extra={"count": len(orders_list), "symbol": symbol, "ticket": ticket},
        )

        return jsonify({"total": len(orders_list), "orders": orders_list})

    except Exception as e:
        return internal_error_response("get_pending_orders", e)


@order_bp.route("/orders/<int:ticket>", methods=["DELETE"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Cancel pending order",
        "description": "Cancel a pending order by ticket number. Only works for pending orders (BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP). Cannot cancel executed market orders or active positions.",
        "parameters": [
            {
                "name": "ticket",
                "in": "path",
                "type": "integer",
                "required": True,
                "description": "Order ticket number to cancel",
                "example": 123456789,
            }
        ],
        "responses": {
            200: {
                "description": "Order cancelled successfully.",
                "schema": {"$ref": "#/definitions/OrderResponse"},
            },
            400: {
                "description": "Invalid ticket or order cannot be cancelled.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            404: {
                "description": "Order not found.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            503: {
                "description": "MT5 unavailable",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def cancel_order(ticket):
    """
    Cancel Pending Order
    ---
    description: Cancel a pending order using TRADE_ACTION_REMOVE.
    """
    try:
        orders = mt5.orders_get(ticket=ticket)

        if orders is None:
            logger.error(f"Failed to check order existence for ticket {ticket}")
            return jsonify(
                {
                    "error": "Failed to retrieve order information",
                    "error_type": "connection_error",
                }
            ), 503

        if len(orders) == 0:
            logger.warning(f"Order {ticket} not found")
            return jsonify(
                {
                    "error": f"Order with ticket {ticket} not found",
                    "error_type": "not_found",
                }
            ), 404

        order = orders[0]

        request_data = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request_data)

        if result is None:
            logger.error(f"order_send returned None for cancel ticket {ticket}")
            return unknown_outcome_response("Cancel order", mt5.last_order_error())

        if not classify_retcode(result.retcode).is_success:
            logger.error(
                f"Failed to cancel order {ticket}: retcode={result.retcode}, comment={result.comment}"
            )
            return mt5_error_response("Cancel order", result)

        logger.info(f"Order {ticket} cancelled successfully")

        return jsonify(
            {"message": "Order cancelled successfully", "result": result._asdict()}
        )

    except Exception as e:
        return internal_error_response("cancel_order", e)


@order_bp.route("/orders/<int:ticket>", methods=["PUT"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Order"],
        "summary": "Modify pending order",
        "description": "Modify a pending order's price, stop loss, or take profit. Only works for pending orders (BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP).",
        "parameters": [
            {
                "name": "ticket",
                "in": "path",
                "type": "integer",
                "required": True,
                "description": "Order ticket number to modify",
                "example": 123456789,
            },
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/OrderModificationRequest"},
            },
        ],
        "responses": {
            200: {
                "description": "Order modified successfully.",
                "schema": {"$ref": "#/definitions/OrderResponse"},
            },
            400: {
                "description": "Invalid parameters or modification rejected.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            404: {
                "description": "Order not found.",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
            503: {
                "description": "MT5 unavailable",
                "schema": {"$ref": "#/definitions/ErrorResponse"},
            },
        },
    }
)
def modify_order(ticket):
    """
    Modify Pending Order
    ---
    description: Modify a pending order's price, SL, or TP using TRADE_ACTION_MODIFY.
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("Modification data is required")

        if "price" not in data and "sl" not in data and "tp" not in data:
            return validation_error_response(
                "At least one of price, sl, or tp must be provided"
            )

        orders = mt5.orders_get(ticket=ticket)

        if orders is None:
            logger.error(f"Failed to check order existence for ticket {ticket}")
            return jsonify(
                {
                    "error": "Failed to retrieve order information",
                    "error_type": "connection_error",
                }
            ), 503

        if len(orders) == 0:
            logger.warning(f"Order {ticket} not found")
            return jsonify(
                {
                    "error": f"Order with ticket {ticket} not found",
                    "error_type": "not_found",
                }
            ), 404

        order = orders[0]

        new_price = float(data["price"]) if "price" in data else order.price_open
        new_sl = float(data["sl"]) if "sl" in data else order.sl
        new_tp = float(data["tp"]) if "tp" in data else order.tp

        if new_price <= 0:
            return validation_error_response("Price must be positive")

        if new_sl is not None and new_sl < 0:
            return validation_error_response(
                "Stop loss must be non-negative (use 0 to remove)"
            )

        if new_tp is not None and new_tp < 0:
            return validation_error_response(
                "Take profit must be non-negative (use 0 to remove)"
            )

        if "price" in data:
            is_valid, error_msg = validate_pending_price(
                order.type, order.symbol, new_price
            )
            if not is_valid:
                return validation_error_response(error_msg)

        if (new_sl is not None and new_sl > 0) or (new_tp is not None and new_tp > 0):
            is_valid, error_msg = validate_sl_tp(
                order.type,
                new_price,
                new_sl if new_sl > 0 else None,
                new_tp if new_tp > 0 else None,
            )
            if not is_valid:
                return validation_error_response(error_msg)

        request_data = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": ticket,
            "price": new_price,
            "sl": new_sl,
            "tp": new_tp,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        apply_expiration(request_data, data, existing_order=order)

        result = mt5.order_send(request_data)

        if result is None:
            logger.error(f"order_send returned None for modify ticket {ticket}")
            return unknown_outcome_response("Modify order", mt5.last_order_error())

        if not classify_retcode(result.retcode).is_success:
            logger.error(
                f"Failed to modify order {ticket}: retcode={result.retcode}, comment={result.comment}"
            )
            return mt5_error_response("Modify order", result)

        logger.info(
            f"Order {ticket} modified successfully: price={new_price}, sl={new_sl}, tp={new_tp}"
        )

        return jsonify(
            {"message": "Order modified successfully", "result": result._asdict()}
        )

    except Exception as e:
        return internal_error_response("modify_order", e)
