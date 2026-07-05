"""Authentication, CORS, and kill-gate hooks."""

import hmac
import logging
import os

from flask import jsonify, request

from kill_switch import kill_switch

logger = logging.getLogger(__name__)

_AUTH_EXEMPT = {"/health/live"}
_AUTH_EXEMPT_PREFIXES = ("/apidocs", "/apispec_", "/flasgger_static/")
_KILL_GATED = {
    "/order",
    "/modify_sl_tp",
    "/position_close_partial",
    "/close_position",
    "/close_all_positions",
}


def install_security_hooks(app):
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        logger.warning("API_KEY is unset; API authentication is disabled")

    @app.before_request
    def enforce_security():
        if api_key and not _is_auth_exempt(request.path):
            supplied = request.headers.get("Authorization", "")
            expected = f"Bearer {api_key}"
            if not hmac.compare_digest(supplied, expected):
                return jsonify(
                    {"error": "Unauthorized", "error_type": "authentication_error"}
                ), 401
        if (
            kill_switch.is_active()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.path in _KILL_GATED
        ):
            return jsonify(
                {
                    "error": "Trading is halted by the kill switch",
                    "error_type": "kill_switch_active",
                }
            ), 423


def _is_auth_exempt(path: str) -> bool:
    return path in _AUTH_EXEMPT or path.startswith(_AUTH_EXEMPT_PREFIXES)
