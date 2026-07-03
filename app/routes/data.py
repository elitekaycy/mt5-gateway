import logging
from datetime import datetime

from mt5_connection import mt5
import pandas as pd
import pytz
from decorators import require_mt5_connection
from errors import internal_error_response, not_found_response, validation_error_response
from flasgger import swag_from
from flask import Blueprint, jsonify, request
from lib import get_timeframe, validate_symbol

data_bp = Blueprint('data', __name__)
logger = logging.getLogger(__name__)

@data_bp.route('/fetch_data_pos', methods=['GET'])
@require_mt5_connection
@swag_from({
    'tags': ['Data'],
    'parameters': [
        {
            'name': 'symbol',
            'in': 'query',
            'type': 'string',
            'required': True,
            'description': 'Symbol name to fetch data for.'
        },
        {
            'name': 'timeframe',
            'in': 'query',
            'type': 'string',
            'required': False,
            'default': 'M1',
            'description': 'Timeframe for the data (e.g., M1, M5, H1).'
        },
        {
            'name': 'num_bars',
            'in': 'query',
            'type': 'integer',
            'required': False,
            'default': 100,
            'description': 'Number of bars to fetch.'
        }
    ],
    'responses': {
        200: {
            'description': 'Data fetched successfully.',
            'schema': {
                'type': 'array',
                'items': {
                    '$ref': '#/definitions/PriceBar'
                }
            }
        },
        400: {
            'description': 'Invalid request parameters.'
        },
        404: {
            'description': 'Failed to get rates data.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def fetch_data_pos_endpoint():
    """
    Fetch Data from Position
    ---
    description: Retrieve historical price data for a given symbol starting from a specific position.
    """
    try:
        symbol = request.args.get('symbol')
        timeframe = request.args.get('timeframe', 'M1')

        if not symbol:
            return validation_error_response("Symbol parameter is required")

        if not validate_symbol(symbol):
            return not_found_response("symbol (not found or not selectable)", symbol)

        try:
            num_bars = int(request.args.get('num_bars', 100))
            mt5_timeframe = get_timeframe(timeframe)
        except ValueError as e:
            return validation_error_response(str(e))

        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, num_bars)
        if rates is None:
            return not_found_response("rates data", symbol)

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        return jsonify(df.to_dict(orient='records'))

    except Exception as e:
        return internal_error_response("fetch_data_pos", e)

@data_bp.route('/fetch_data_range', methods=['GET'])
@require_mt5_connection
@swag_from({
    'tags': ['Data'],
    'parameters': [
        {
            'name': 'symbol',
            'in': 'query',
            'type': 'string',
            'required': True,
            'description': 'Symbol name to fetch data for.'
        },
        {
            'name': 'timeframe',
            'in': 'query',
            'type': 'string',
            'required': False,
            'default': 'M1',
            'description': 'Timeframe for the data (e.g., M1, M5, H1).'
        },
        {
            'name': 'start',
            'in': 'query',
            'type': 'string',
            'required': True,
            'format': 'date-time',
            'description': 'Start datetime in ISO format.'
        },
        {
            'name': 'end',
            'in': 'query',
            'type': 'string',
            'required': True,
            'format': 'date-time',
            'description': 'End datetime in ISO format.'
        }
    ],
    'responses': {
        200: {
            'description': 'Data fetched successfully.',
            'schema': {
                'type': 'array',
                'items': {
                    '$ref': '#/definitions/PriceBar'
                }
            }
        },
        400: {
            'description': 'Invalid request parameters.'
        },
        404: {
            'description': 'Failed to get rates data.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def fetch_data_range_endpoint():
    """
    Fetch Data within a Date Range
    ---
    description: Retrieve historical price data for a given symbol within a specified date range.
    """
    try:
        symbol = request.args.get('symbol')
        timeframe = request.args.get('timeframe', 'M1')
        start_str = request.args.get('start')
        end_str = request.args.get('end')

        if not all([symbol, start_str, end_str]):
            return validation_error_response("Symbol, start, and end parameters are required")

        if not validate_symbol(symbol):
            return not_found_response("symbol (not found or not selectable)", symbol)

        try:
            mt5_timeframe = get_timeframe(timeframe)

            utc = pytz.UTC
            start_date = utc.localize(datetime.fromisoformat(start_str.replace('Z', '+00:00')))
            end_date = utc.localize(datetime.fromisoformat(end_str.replace('Z', '+00:00')))
        except ValueError as e:
            return validation_error_response(f"Invalid parameter format: {str(e)}")

        logger.info(f"Fetching rates for {symbol}, timeframe={timeframe}, start={start_date}, end={end_date}")
        rates = mt5.copy_rates_range(symbol, mt5_timeframe, start_date, end_date)
        if rates is None:
            error_code, error_str = mt5.last_error()
            logger.error(f"MT5 copy_rates_range failed: {error_str} (code: {error_code})")
            return not_found_response("rates data", symbol)

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        return jsonify(df.to_dict(orient='records'))

    except Exception as e:
        return internal_error_response("fetch_data_range", e)
