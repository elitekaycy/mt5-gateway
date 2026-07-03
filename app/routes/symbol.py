import logging

from decorators import require_mt5_connection
from errors import internal_error_response, not_found_response
from flasgger import swag_from
from flask import Blueprint, jsonify, request
from lib import validate_symbol
from mt5_connection import mt5

symbol_bp = Blueprint("symbol", __name__)
logger = logging.getLogger(__name__)


@symbol_bp.route("/symbols", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Symbol"],
        "parameters": [
            {
                "name": "search",
                "in": "query",
                "type": "string",
                "required": False,
                "description": 'Filter symbols by name (e.g., "*EUR*", "USD*").',
            }
        ],
        "responses": {
            200: {
                "description": "List of symbols retrieved successfully.",
                "schema": {"$ref": "#/definitions/SymbolsListResponse"},
            },
            500: {"description": "Internal server error."},
        },
    }
)
def get_symbols_endpoint():
    """
    Get All Available Symbols
    ---
    description: Retrieve a list of all symbol names available on the MT5 server.
    """
    try:
        search = request.args.get("search", "*")
        symbols = mt5.symbols_get(group=search)

        if symbols is None:
            return jsonify({"total": 0, "symbols": []}), 200

        symbol_names = [s.name for s in symbols]
        return jsonify({"total": len(symbol_names), "symbols": sorted(symbol_names)})

    except Exception as e:
        return internal_error_response("get_symbols", e)


@symbol_bp.route("/symbol_info_tick/<symbol>", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Symbol"],
        "parameters": [
            {
                "name": "symbol",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "Symbol name to retrieve tick information.",
            }
        ],
        "responses": {
            200: {
                "description": "Tick information retrieved successfully.",
                "schema": {"$ref": "#/definitions/SymbolTickInfo"},
            },
            404: {"description": "Failed to get symbol tick info."},
        },
    }
)
def get_symbol_info_tick_endpoint(symbol):
    """
    Get Symbol Tick Information
    ---
    description: Retrieve the latest tick information for a given symbol.
    """
    try:
        if not validate_symbol(symbol):
            return not_found_response("symbol (not found or not selectable)", symbol)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return not_found_response("symbol tick info", symbol)

        return jsonify(tick._asdict())

    except Exception as e:
        return internal_error_response("get_symbol_info_tick", e)


@symbol_bp.route("/symbol_info/<symbol>", methods=["GET"])
@require_mt5_connection
@swag_from(
    {
        "tags": ["Symbol"],
        "parameters": [
            {
                "name": "symbol",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "Symbol name to retrieve information.",
            }
        ],
        "responses": {
            200: {
                "description": "Symbol information retrieved successfully.",
                "schema": {"$ref": "#/definitions/SymbolInfo"},
            },
            404: {"description": "Failed to get symbol info."},
        },
    }
)
def get_symbol_info(symbol):
    """
    Get Symbol Information
    ---
    description: Retrieve detailed information for a given symbol.
    """
    try:
        if not validate_symbol(symbol):
            return not_found_response("symbol (not found or not selectable)", symbol)

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return not_found_response("symbol info", symbol)

        return jsonify(symbol_info._asdict())

    except Exception as e:
        return internal_error_response("get_symbol_info", e)
