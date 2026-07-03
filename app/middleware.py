import uuid

from flask import g, request


class RequestIDMiddleware:
    def __init__(self, app):
        self.app = app
        app.before_request(self.before_request)
        app.after_request(self.after_request)

    def before_request(self):
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    def after_request(self, response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response
