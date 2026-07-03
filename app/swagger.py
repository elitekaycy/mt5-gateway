import os

from version import get_version

swagger_scheme = os.environ.get("SWAGGER_SCHEME", "http")
schemes = [swagger_scheme] if swagger_scheme in ["http", "https"] else ["http", "https"]

swagger_config = {
    "swagger": "2.0",
    "info": {
        "title": "MetaTrader5 API",
        "description": "API documentation for MetaTrader5 Flask application.",
        "version": get_version(),
    },
    "basePath": "/",
    "schemes": schemes,
    "securityDefinitions": {
        "ApiKeyAuth": {"type": "apiKey", "name": "Authorization", "in": "header"}
    },
    "security": [{"ApiKeyAuth": []}],
    "definitions": {
        "OrderRequest": {
            "type": "object",
            "required": ["symbol", "volume", "type"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol (e.g., EURUSD, GBPUSD)",
                    "example": "EURUSD",
                },
                "volume": {
                    "type": "number",
                    "description": "Order volume in lots (must comply with symbol min/max/step)",
                    "example": 0.1,
                    "minimum": 0.01,
                },
                "type": {
                    "type": "string",
                    "enum": [
                        "BUY",
                        "SELL",
                        "BUY_LIMIT",
                        "SELL_LIMIT",
                        "BUY_STOP",
                        "SELL_STOP",
                    ],
                    "description": "Order type:\n- BUY: Market buy (immediate execution at ask)\n- SELL: Market sell (immediate execution at bid)\n- BUY_LIMIT: Pending buy below market\n- SELL_LIMIT: Pending sell above market\n- BUY_STOP: Pending buy above market (breakout)\n- SELL_STOP: Pending sell below market (breakout)",
                },
                "price": {
                    "type": "number",
                    "description": "Price (REQUIRED for pending orders, ignored for market orders)",
                    "example": 1.0850,
                },
                "sl": {
                    "type": "number",
                    "description": "Stop loss price (optional). BUY orders: must be below entry. SELL orders: must be above entry.",
                    "example": 1.0800,
                },
                "tp": {
                    "type": "number",
                    "description": "Take profit price (optional). BUY orders: must be above entry. SELL orders: must be below entry.",
                    "example": 1.0900,
                },
                "deviation": {
                    "type": "integer",
                    "description": "Maximum price deviation in points (for market orders)",
                    "default": 20,
                    "example": 20,
                },
                "magic": {
                    "type": "integer",
                    "description": "Magic number to identify this order/strategy",
                    "default": 0,
                    "example": 12345,
                },
                "comment": {
                    "type": "string",
                    "description": "Order comment",
                    "default": "",
                    "example": "My strategy order",
                },
                "client_order_id": {
                    "type": "string",
                    "maxLength": 128,
                    "description": "Stable idempotency key for this intended trade. Reusing it with the same request replays the original response; different parameters return 409.",
                    "example": "strategy-a-20260703-0001",
                },
                "type_filling": {
                    "type": "string",
                    "enum": ["IOC", "FOK", "RETURN"],
                    "description": "Order filling policy:\n- IOC (Immediate or Cancel): Fill available volume, cancel remainder\n- FOK (Fill or Kill): Fill entire volume or cancel\n- RETURN: Fill available volume, return remainder as limit order",
                    "default": "IOC",
                },
            },
        },
        "OrderCheckRequest": {
            "type": "object",
            "required": ["symbol", "volume", "type"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["DEAL", "PENDING"],
                    "description": "Order action:\n- DEAL: Immediate market execution\n- PENDING: Place as pending order",
                    "default": "DEAL",
                },
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                    "example": "EURUSD",
                },
                "volume": {
                    "type": "number",
                    "description": "Order volume in lots",
                    "example": 0.1,
                },
                "type": {
                    "type": "string",
                    "enum": [
                        "BUY",
                        "SELL",
                        "BUY_LIMIT",
                        "SELL_LIMIT",
                        "BUY_STOP",
                        "SELL_STOP",
                    ],
                    "description": "Order type",
                },
                "price": {
                    "type": "number",
                    "description": "Price (required for pending orders)",
                    "example": 1.0850,
                },
                "sl": {
                    "type": "number",
                    "description": "Stop loss price",
                    "example": 1.0800,
                },
                "tp": {
                    "type": "number",
                    "description": "Take profit price",
                    "example": 1.0900,
                },
                "deviation": {"type": "integer", "default": 20},
                "magic": {"type": "integer", "default": 0},
                "comment": {"type": "string", "default": ""},
            },
        },
        "MarginCalculationRequest": {
            "type": "object",
            "required": ["symbol", "volume", "type", "price"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["DEAL", "PENDING"],
                    "default": "DEAL",
                },
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                    "example": "EURUSD",
                },
                "volume": {
                    "type": "number",
                    "description": "Order volume in lots",
                    "example": 0.1,
                },
                "type": {
                    "type": "string",
                    "enum": [
                        "BUY",
                        "SELL",
                        "BUY_LIMIT",
                        "SELL_LIMIT",
                        "BUY_STOP",
                        "SELL_STOP",
                    ],
                },
                "price": {
                    "type": "number",
                    "description": "Price to calculate margin at",
                    "example": 1.0850,
                },
            },
        },
        "ProfitCalculationRequest": {
            "type": "object",
            "required": ["symbol", "volume", "type", "price_open", "price_close"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["DEAL", "PENDING"],
                    "default": "DEAL",
                },
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                    "example": "EURUSD",
                },
                "volume": {
                    "type": "number",
                    "description": "Position volume in lots",
                    "example": 0.1,
                },
                "type": {
                    "type": "string",
                    "enum": ["BUY", "SELL"],
                    "description": "Position type (only BUY or SELL for profit calculation)",
                },
                "price_open": {
                    "type": "number",
                    "description": "Entry price",
                    "example": 1.0850,
                },
                "price_close": {
                    "type": "number",
                    "description": "Exit price",
                    "example": 1.0900,
                },
            },
        },
        "OrderResponse": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "example": "Order executed successfully"},
                "result": {
                    "type": "object",
                    "properties": {
                        "retcode": {
                            "type": "integer",
                            "description": "Return code (0 = TRADE_RETCODE_DONE, success)",
                            "example": 0,
                        },
                        "order": {
                            "type": "integer",
                            "description": "Order ticket number",
                            "example": 123456789,
                        },
                        "deal": {
                            "type": "integer",
                            "description": "Deal ticket (for executed orders)",
                            "example": 123456790,
                        },
                        "volume": {
                            "type": "number",
                            "description": "Order volume",
                            "example": 0.1,
                        },
                        "price": {
                            "type": "number",
                            "description": "Execution/order price",
                            "example": 1.0850,
                        },
                        "symbol": {"type": "string", "example": "EURUSD"},
                        "comment": {
                            "type": "string",
                            "description": "MT5 response comment",
                            "example": "Request executed",
                        },
                        "request_id": {"type": "integer"},
                    },
                },
            },
        },
        "OrderCheckResponse": {
            "type": "object",
            "properties": {
                "valid": {
                    "type": "boolean",
                    "description": "Whether order would be accepted",
                },
                "retcode": {"type": "integer", "description": "MT5 return code"},
                "balance": {
                    "type": "number",
                    "description": "Account balance after order",
                },
                "equity": {
                    "type": "number",
                    "description": "Account equity after order",
                },
                "profit": {"type": "number", "description": "Expected profit/loss"},
                "margin": {
                    "type": "number",
                    "description": "Margin required for this order",
                },
                "margin_free": {
                    "type": "number",
                    "description": "Free margin after order",
                },
                "margin_level": {
                    "type": "number",
                    "description": "Margin level percentage after order",
                },
                "comment": {
                    "type": "string",
                    "description": "MT5 comment/error message",
                },
            },
        },
        "MarginCalculationResponse": {
            "type": "object",
            "properties": {
                "margin": {
                    "type": "number",
                    "description": "Required margin in account currency",
                    "example": 100.50,
                }
            },
        },
        "ProfitCalculationResponse": {
            "type": "object",
            "properties": {
                "profit": {
                    "type": "number",
                    "description": "Profit/loss in account currency (negative = loss). Does NOT include swap/commission.",
                    "example": 50.0,
                }
            },
        },
        "PendingOrder": {
            "type": "object",
            "properties": {
                "ticket": {
                    "type": "integer",
                    "description": "Order ticket number",
                    "example": 123456789,
                },
                "time_setup": {
                    "type": "integer",
                    "description": "Order setup timestamp (Unix)",
                    "example": 1640000000,
                },
                "type": {
                    "type": "integer",
                    "description": "Order type code (2=BUY_LIMIT, 3=SELL_LIMIT, 4=BUY_STOP, 5=SELL_STOP)",
                    "example": 2,
                },
                "type_str": {
                    "type": "string",
                    "description": "Human-readable order type",
                    "example": "BUY_LIMIT",
                    "enum": [
                        "BUY_LIMIT",
                        "SELL_LIMIT",
                        "BUY_STOP",
                        "SELL_STOP",
                        "BUY_STOP_LIMIT",
                        "SELL_STOP_LIMIT",
                    ],
                },
                "symbol": {"type": "string", "example": "EURUSD"},
                "volume_initial": {
                    "type": "number",
                    "description": "Initial order volume",
                    "example": 0.1,
                },
                "volume_current": {
                    "type": "number",
                    "description": "Current remaining volume",
                    "example": 0.1,
                },
                "price_open": {
                    "type": "number",
                    "description": "Trigger price",
                    "example": 1.0850,
                },
                "sl": {
                    "type": "number",
                    "description": "Stop loss price (0 if not set)",
                    "example": 1.0800,
                },
                "tp": {
                    "type": "number",
                    "description": "Take profit price (0 if not set)",
                    "example": 1.0900,
                },
                "magic": {
                    "type": "integer",
                    "description": "Magic number",
                    "example": 12345,
                },
                "comment": {"type": "string", "example": "My pending order"},
            },
        },
        "PendingOrdersResponse": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "integer",
                    "description": "Number of pending orders",
                    "example": 2,
                },
                "orders": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/PendingOrder"},
                },
            },
        },
        "AccountInfo": {
            "type": "object",
            "properties": {
                "login": {
                    "type": "integer",
                    "description": "Account number",
                    "example": 12345678,
                },
                "balance": {
                    "type": "number",
                    "description": "Account balance (deposits + closed P/L)",
                    "example": 10000.00,
                },
                "equity": {
                    "type": "number",
                    "description": "Current equity (balance + floating P/L)",
                    "example": 10050.00,
                },
                "margin": {
                    "type": "number",
                    "description": "Margin currently used by open positions",
                    "example": 100.00,
                },
                "margin_free": {
                    "type": "number",
                    "description": "Free margin available for new positions",
                    "example": 9950.00,
                },
                "margin_level": {
                    "type": "number",
                    "description": "Margin level percentage (equity/margin * 100). Values below 100% trigger margin calls.",
                    "example": 10050.00,
                },
                "profit": {
                    "type": "number",
                    "description": "Current floating profit/loss from open positions",
                    "example": 50.00,
                },
                "currency": {
                    "type": "string",
                    "description": "Account currency",
                    "example": "USD",
                },
                "leverage": {
                    "type": "integer",
                    "description": "Account leverage (e.g., 100 = 1:100)",
                    "example": 100,
                },
                "server": {
                    "type": "string",
                    "description": "Broker server name",
                    "example": "MetaQuotes-Demo",
                },
                "trade_mode": {
                    "type": "integer",
                    "enum": [0, 1, 2],
                    "description": "Account trade mode:\n- 0: DEMO account\n- 1: CONTEST account\n- 2: REAL account",
                    "example": 0,
                },
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "error_type": {
                    "type": "string",
                    "enum": [
                        "validation_error",
                        "mt5_rejected",
                        "connection_error",
                        "not_found",
                    ],
                    "description": "Error category",
                },
                "details": {
                    "type": "object",
                    "description": "Additional error details",
                },
                "mt5_error": {
                    "type": "object",
                    "description": "MT5-specific error information",
                    "properties": {
                        "retcode": {
                            "type": "integer",
                            "description": "MT5 return code",
                        },
                        "comment": {
                            "type": "string",
                            "description": "MT5 error comment",
                        },
                        "error_code": {
                            "type": "integer",
                            "description": "MT5 error code",
                        },
                        "error_string": {
                            "type": "string",
                            "description": "MT5 error description",
                        },
                    },
                },
                "request_id": {"type": "string", "description": "Request tracking ID"},
            },
        },
        "PriceBar": {
            "type": "object",
            "properties": {
                "time": {"type": "string", "format": "date-time"},
                "open": {"type": "number"},
                "high": {"type": "number"},
                "low": {"type": "number"},
                "close": {"type": "number"},
                "tick_volume": {"type": "integer"},
                "spread": {"type": "integer"},
                "real_volume": {"type": "integer"},
            },
        },
        "LastErrorResponse": {
            "type": "object",
            "properties": {
                "error_code": {"type": "integer"},
                "error_message": {"type": "string"},
            },
        },
        "LastErrorStringResponse": {
            "type": "object",
            "properties": {"error_message": {"type": "string"}},
        },
        "HealthResponse": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "mt5_status": {"type": "string"},
                "mt5_account": {"type": "integer"},
                "last_error": {"type": "string"},
                "uptime_seconds": {"type": "number"},
            },
        },
        "ReadinessResponse": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "mt5_status": {"type": "string"},
                "error": {"type": "string"},
            },
        },
        "LivenessResponse": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
        },
        "DealInfo": {
            "type": "object",
            "properties": {
                "ticket": {"type": "integer"},
                "symbol": {"type": "string"},
                "type": {"type": "string"},
                "volume": {"type": "number"},
                "open_time": {"type": "string", "format": "date-time"},
                "close_time": {"type": "string", "format": "date-time"},
                "open_price": {"type": "number"},
                "close_price": {"type": "number"},
                "profit": {"type": "number"},
                "commission": {"type": "number"},
                "swap": {"type": "number"},
                "comment": {"type": "string"},
            },
        },
        "HistoryOrder": {
            "type": "object",
            "properties": {
                "ticket": {"type": "integer"},
                "time_setup": {"type": "integer"},
                "time_done": {"type": "integer"},
                "type": {"type": "integer"},
                "state": {"type": "integer"},
                "symbol": {"type": "string"},
                "volume_initial": {"type": "number"},
                "volume_current": {"type": "number"},
                "price_open": {"type": "number"},
                "price_current": {"type": "number"},
                "sl": {"type": "number"},
                "tp": {"type": "number"},
                "price_stoplimit": {"type": "number"},
                "magic": {"type": "integer"},
                "comment": {"type": "string"},
            },
        },
        "OrderModificationRequest": {
            "type": "object",
            "properties": {
                "price": {
                    "type": "number",
                    "description": "New order trigger price (optional)",
                    "example": 1.0860,
                },
                "sl": {
                    "type": "number",
                    "description": "New stop loss price (optional, use 0 to remove)",
                    "example": 1.0810,
                },
                "tp": {
                    "type": "number",
                    "description": "New take profit price (optional, use 0 to remove)",
                    "example": 1.0910,
                },
            },
        },
        "ClosePositionRequest": {
            "type": "object",
            "required": ["position"],
            "properties": {
                "position": {
                    "type": "object",
                    "required": ["type", "ticket", "symbol", "volume"],
                    "properties": {
                        "type": {"type": "integer"},
                        "ticket": {"type": "integer"},
                        "symbol": {"type": "string"},
                        "volume": {"type": "number"},
                    },
                }
            },
        },
        "MT5Result": {
            "type": "object",
            "properties": {
                "retcode": {"type": "integer"},
                "deal": {"type": "integer"},
                "order": {"type": "integer"},
                "volume": {"type": "number"},
                "price": {"type": "number"},
                "bid": {"type": "number"},
                "ask": {"type": "number"},
                "comment": {"type": "string"},
                "request_id": {"type": "integer"},
                "retcode_external": {"type": "integer"},
            },
        },
        "ClosePositionResponse": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "result": {"$ref": "#/definitions/MT5Result"},
            },
        },
        "ClosePositionPartialRequest": {
            "type": "object",
            "required": ["ticket", "symbol", "volume", "type"],
            "properties": {
                "ticket": {"type": "integer"},
                "symbol": {"type": "string"},
                "volume": {"type": "number"},
                "type": {"type": "integer"},
                "deviation": {"type": "integer", "default": 20},
                "magic": {"type": "integer", "default": 0},
                "comment": {"type": "string", "default": "Partial close"},
            },
        },
        "ClosePositionPartialResponse": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "result": {"$ref": "#/definitions/MT5Result"},
            },
        },
        "CloseAllPositionsRequest": {
            "type": "object",
            "properties": {
                "order_type": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "all"],
                    "default": "all",
                },
                "magic": {"type": "integer"},
            },
        },
        "CloseAllPositionsResponse": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "results": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/MT5Result"},
                },
            },
        },
        "ModifySLTPRequest": {
            "type": "object",
            "required": ["position"],
            "properties": {
                "position": {"type": "integer"},
                "sl": {
                    "type": "number",
                    "description": "New stop loss. Omission preserves the existing stop.",
                },
                "tp": {
                    "type": "number",
                    "description": "New take profit. Omission preserves the existing target.",
                },
                "clear_sl": {
                    "type": "boolean",
                    "description": "Explicitly remove the existing stop loss.",
                },
                "clear_tp": {
                    "type": "boolean",
                    "description": "Explicitly remove the existing take profit.",
                },
            },
        },
        "ModifySLTPResponse": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "result": {"$ref": "#/definitions/MT5Result"},
            },
        },
        "PositionInfo": {
            "type": "object",
            "properties": {
                "ticket": {"type": "integer"},
                "time": {"type": "integer"},
                "time_msc": {"type": "integer"},
                "time_update": {"type": "integer"},
                "time_update_msc": {"type": "integer"},
                "type": {"type": "integer"},
                "magic": {"type": "integer"},
                "identifier": {"type": "integer"},
                "reason": {"type": "integer"},
                "volume": {"type": "number"},
                "price_open": {"type": "number"},
                "sl": {"type": "number"},
                "tp": {"type": "number"},
                "price_current": {"type": "number"},
                "swap": {"type": "number"},
                "profit": {"type": "number"},
                "symbol": {"type": "string"},
                "comment": {"type": "string"},
                "external_id": {"type": "string"},
            },
        },
        "PositionsResponse": {
            "type": "object",
            "properties": {
                "positions": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/PositionInfo"},
                }
            },
        },
        "PositionsTotalResponse": {
            "type": "object",
            "properties": {"total": {"type": "integer"}},
        },
        "SymbolsListResponse": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
        },
        "SymbolTickInfo": {
            "type": "object",
            "properties": {
                "bid": {"type": "number"},
                "ask": {"type": "number"},
                "last": {"type": "number"},
                "volume": {"type": "integer"},
                "time": {"type": "integer"},
                "time_msc": {"type": "integer"},
                "flags": {"type": "integer"},
                "volume_real": {"type": "number"},
            },
        },
        "SymbolInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string"},
                "description": {"type": "string"},
                "volume_min": {"type": "number"},
                "volume_max": {"type": "number"},
                "volume_step": {"type": "number"},
                "price_digits": {"type": "integer"},
                "spread": {"type": "number"},
                "digits": {"type": "integer"},
                "point": {"type": "number"},
                "trade_tick_value": {"type": "number"},
                "trade_tick_size": {"type": "number"},
                "trade_contract_size": {"type": "number"},
                "points": {"type": "integer"},
                "trade_mode": {"type": "integer"},
            },
        },
    },
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: True,  # Include all routes
            "model_filter": lambda tag: True,  # Include all models
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "headers": [],
}
