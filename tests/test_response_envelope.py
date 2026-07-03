from flask import Flask, jsonify
from responses import install_response_envelope


def test_response_envelope_handles_success_lists_and_errors():
    app = Flask(__name__)
    install_response_envelope(app)
    app.add_url_rule("/items", "items", lambda: jsonify([1, 2]))
    app.add_url_rule(
        "/error",
        "error",
        lambda: (jsonify({"error": "bad", "error_type": "test"}), 400),
    )
    client = app.test_client()

    assert client.get("/items").get_json() == {"ok": True, "data": [1, 2]}
    assert client.get("/error").get_json()["ok"] is False
