"""Consistent JSON response envelope middleware."""

from flask import current_app, g


def install_response_envelope(app):
    @app.after_request
    def envelope(response):
        if not response.is_json:
            return response
        payload = response.get_json()
        if isinstance(payload, list):
            payload = {"data": payload}
        elif not isinstance(payload, dict):
            payload = {"data": payload}
        payload.setdefault("ok", response.status_code < 400)
        request_id = getattr(g, "request_id", None)
        if request_id:
            payload.setdefault("request_id", request_id)
        response.set_data(current_app.json.dumps(payload))
        response.content_type = "application/json"
        return response
