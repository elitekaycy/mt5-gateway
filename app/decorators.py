import logging
from functools import wraps

from flask import g, jsonify
from mt5_connection import MT5Connection

logger = logging.getLogger(__name__)


def require_mt5_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = MT5Connection.get_instance()

        if not conn.ensure_connection():
            request_id = getattr(g, "request_id", None)
            error_response = {
                "error": "MT5 unavailable",
                "detail": conn.get_last_error(),
                "mt5_status": conn.get_status().value,
            }
            if request_id:
                error_response["request_id"] = request_id

            logger.error(
                "MT5 connection unavailable for request",
                extra={"request_id": request_id, "last_error": conn.get_last_error()},
            )
            return jsonify(error_response), 503

        return f(*args, **kwargs)

    return decorated_function
