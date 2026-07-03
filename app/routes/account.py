import logging

from mt5_connection import mt5
from decorators import require_mt5_connection
from errors import internal_error_response
from flasgger import swag_from
from flask import Blueprint, g, jsonify

account_bp = Blueprint('account', __name__)
logger = logging.getLogger(__name__)

@account_bp.route('/account', methods=['GET'])
@require_mt5_connection
@swag_from({
    'tags': ['Account'],
    'summary': 'Get account information',
    'description': 'Retrieve current account state including balance, equity, margin, and leverage. This is a point-in-time snapshot - values change as positions and market move.',
    'responses': {
        200: {
            'description': 'Account information retrieved successfully.',
            'schema': {
                '$ref': '#/definitions/AccountInfo'
            }
        },
        503: {
            'description': 'MT5 unavailable or failed to get account info.',
            'schema': {
                '$ref': '#/definitions/ErrorResponse'
            }
        }
    }
})
def get_account_info():
    """
    Get Account Information
    ---
    description: Retrieve current account information including balance, equity, margin, and other details.
    """
    try:
        account_info = mt5.account_info()
        if account_info is None:
            request_id = getattr(g, 'request_id', None)
            error_code, error_str = mt5.last_error()

            response = {
                "error": "Failed to get account info",
                "error_type": "connection_error",
                "mt5_error": {
                    "error_code": error_code,
                    "error_string": error_str
                }
            }

            if request_id:
                response["request_id"] = request_id

            logger.error(f"Failed to get account info: {error_str}", extra={
                "error_code": error_code,
                "request_id": request_id
            })

            return jsonify(response), 503

        logger.info(f"Account info retrieved: login={account_info.login}, equity={account_info.equity}, margin_free={account_info.margin_free}")

        return jsonify(account_info._asdict())

    except Exception as e:
        return internal_error_response("get_account_info", e)
