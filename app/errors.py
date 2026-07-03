import logging

from flask import g, jsonify
from retcodes import RetcodeClass, classify_retcode

logger = logging.getLogger(__name__)


def _get_request_id():
    return getattr(g, 'request_id', None)


def mt5_error_response(operation, result):
    """
    Build error response for MT5 operation failures.

    Args:
        operation: Description of the operation that failed
        result: MT5 result object from order_send or similar

    Returns:
        tuple: (jsonify response, status_code)
    """
    request_id = _get_request_id()

    info = classify_retcode(result.retcode)
    status_code, error_type = {
        RetcodeClass.RETRYABLE: (409, "retryable"),
        RetcodeClass.AMBIGUOUS: (502, "unknown_outcome"),
        RetcodeClass.PERMANENT: (400, "mt5_rejected"),
    }.get(info.classification, (500, "invalid_error_classification"))

    response = {
        "error": f"{operation} failed: {result.comment}",
        "error_type": error_type,
        "mt5_error": {
            "retcode": result.retcode,
            "retcode_name": info.name,
            "comment": result.comment,
        }
    }
    if info.is_ambiguous:
        response["retry_guidance"] = (
            "Reconcile positions and order/deal history before retrying."
        )

    if request_id:
        response["request_id"] = request_id

    logger.error(f"MT5 error: {operation}", extra={
        "operation": operation,
        "retcode": result.retcode,
        "retcode_name": info.name,
        "request_id": request_id
    })

    return jsonify(response), status_code


def unknown_outcome_response(operation, last_error=None):
    """Report an order whose broker-side outcome cannot be determined."""
    request_id = _get_request_id()
    response = {
        "error": f"{operation} outcome is unknown",
        "error_type": "unknown_outcome",
        "retry_guidance": (
            "Reconcile positions and order/deal history before retrying."
        ),
    }
    if last_error is not None:
        response["mt5_error"] = {"last_error": last_error}
    if request_id:
        response["request_id"] = request_id

    logger.error(
        "Unknown MT5 outcome: %s",
        operation,
        extra={"operation": operation, "request_id": request_id},
    )
    return jsonify(response), 502


def mt5_connection_error_response(operation, last_error=None):
    """Report an MT5 IPC failure without misrepresenting it as empty data."""
    request_id = _get_request_id()
    response = {
        "error": f"{operation} failed because MT5 is unavailable",
        "error_type": "connection_error",
        "mt5_error": {"last_error": last_error},
    }
    if request_id:
        response["request_id"] = request_id
    logger.error(
        "MT5 connection error: %s",
        operation,
        extra={"operation": operation, "request_id": request_id},
    )
    return jsonify(response), 503


def internal_error_response(operation, exception):
    """
    Build error response for internal server errors.

    Args:
        operation: Description of what was being attempted
        exception: The exception that occurred

    Returns:
        tuple: (jsonify response, 500)
    """
    request_id = _get_request_id()

    response = {
        "error": "Internal server error",
        "operation": operation,
        "detail": str(exception)
    }

    if request_id:
        response["request_id"] = request_id

    logger.exception(f"Internal error during {operation}", extra={
        "operation": operation,
        "request_id": request_id
    })

    return jsonify(response), 500


def validation_error_response(message, details=None):
    """
    Build error response for request validation failures.

    Args:
        message: Human-readable error message
        details: Optional dict with additional validation error details

    Returns:
        tuple: (jsonify response, 400)
    """
    request_id = _get_request_id()

    response = {
        "error": message,
        "error_type": "validation_error"
    }

    if details:
        response["details"] = details

    if request_id:
        response["request_id"] = request_id

    logger.warning(f"Validation error: {message}", extra={
        "request_id": request_id,
        "details": details
    })

    return jsonify(response), 400


def not_found_response(resource, identifier=None):
    """
    Build error response for resource not found.

    Args:
        resource: Type of resource (e.g., "symbol", "position")
        identifier: Optional identifier of the missing resource

    Returns:
        tuple: (jsonify response, 404)
    """
    request_id = _get_request_id()

    if identifier:
        message = f"{resource.capitalize()} not found: {identifier}"
    else:
        message = f"{resource.capitalize()} not found"

    response = {
        "error": message,
        "error_type": "not_found"
    }

    if request_id:
        response["request_id"] = request_id

    return jsonify(response), 404
