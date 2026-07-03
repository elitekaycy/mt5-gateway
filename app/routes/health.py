import time

from mt5_connection import mt5
from flasgger import swag_from
from flask import Blueprint, jsonify

from mt5_connection import MT5Connection

health_bp = Blueprint('health', __name__)

_start_time = time.time()


@health_bp.route('/health')
@swag_from({
    'tags': ['Health'],
    'responses': {
        200: {
            'description': 'Health check successful',
            'schema': {
                '$ref': '#/definitions/HealthResponse'
            }
        }
    }
})
def health_check():
    """
    Full Health Check
    ---
    description: Comprehensive health check including MT5 connection validation.
    """
    conn = MT5Connection.get_instance()
    uptime = time.time() - _start_time

    response = {
        "status": "healthy",
        "mt5_status": conn.get_status().value,
        "uptime_seconds": round(uptime, 2)
    }

    if conn.is_connected():
        try:
            account_info = mt5.account_info()
            if account_info:
                response["mt5_account"] = account_info.login
            else:
                response["mt5_account"] = None
        except Exception:
            response["mt5_account"] = None
    else:
        response["mt5_account"] = None

    last_error = conn.get_last_error()
    if last_error:
        response["last_error"] = last_error
    else:
        response["last_error"] = None

    return jsonify(response), 200


@health_bp.route('/health/ready')
@swag_from({
    'tags': ['Health'],
    'responses': {
        200: {
            'description': 'Service is ready',
            'schema': {
                '$ref': '#/definitions/ReadinessResponse'
            }
        },
        503: {
            'description': 'Service not ready (MT5 disconnected)',
            'schema': {
                '$ref': '#/definitions/ReadinessResponse'
            }
        }
    }
})
def ready_check():
    """
    Readiness Check
    ---
    description: Kubernetes-style readiness probe. Returns 503 if MT5 is unavailable.
    """
    conn = MT5Connection.get_instance()

    if conn.is_connected():
        return jsonify({
            "status": "ready",
            "mt5_status": conn.get_status().value
        }), 200
    else:
        return jsonify({
            "status": "not_ready",
            "mt5_status": conn.get_status().value,
            "error": conn.get_last_error()
        }), 503


@health_bp.route('/health/live')
@swag_from({
    'tags': ['Health'],
    'responses': {
        200: {
            'description': 'Service is alive',
            'schema': {
                '$ref': '#/definitions/LivenessResponse'
            }
        }
    }
})
def liveness_check():
    """
    Liveness Check
    ---
    description: Kubernetes-style liveness probe. Always returns 200 if process is running.
    """
    return jsonify({"status": "alive"}), 200
