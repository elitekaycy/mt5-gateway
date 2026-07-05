from types import SimpleNamespace

from flask import Flask, g

from errors import (
    internal_error_response,
    mt5_connection_error_response,
    mt5_error_response,
    not_found_response,
    unknown_outcome_response,
    validation_error_response,
)


def test_error_helpers_return_consistent_envelopes():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.request_id = "request-1"

        response, status = validation_error_response("bad", {"field": "volume"})
        assert status == 400
        assert response.get_json()["error_type"] == "validation_error"

        response, status = not_found_response("position", 42)
        assert status == 404
        assert response.get_json()["request_id"] == "request-1"

        response, status = mt5_connection_error_response("history", (-1, "down"))
        assert status == 503
        assert response.get_json()["error_type"] == "connection_error"

        response, status = unknown_outcome_response("order", (-1, "timeout"))
        assert status == 502
        assert response.get_json()["error_type"] == "unknown_outcome"

        response, status = internal_error_response("test", ValueError("broken"))
        assert status == 500
        assert response.get_json()["operation"] == "test"


def test_mt5_error_response_uses_retcode_taxonomy():
    app = Flask(__name__)
    with app.test_request_context("/"):
        permanent = SimpleNamespace(retcode=10019, comment="no money")
        response, status = mt5_error_response("order", permanent)
        assert status == 400
        assert response.get_json()["mt5_error"]["retcode_name"] == "NO_MONEY"

        retryable = SimpleNamespace(retcode=10004, comment="requote")
        response, status = mt5_error_response("order", retryable)
        assert status == 409
        assert response.get_json()["error_type"] == "retryable"

        ambiguous = SimpleNamespace(retcode=99999, comment="unknown")
        response, status = mt5_error_response("order", ambiguous)
        assert status == 502
        assert "reconcile" in response.get_json()["retry_guidance"].lower()
