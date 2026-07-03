import logging
import os
import sys

from flask import g, has_request_context
from pythonjsonlogger.json import JsonFormatter


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", None)
        else:
            record.request_id = None
        return True


def configure_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    formatter = JsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s %(request_id)s",
        rename_fields={"levelname": "level", "name": "module", "asctime": "timestamp"},
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    logging.basicConfig(level=getattr(logging, log_level), handlers=[handler])

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("flasgger").setLevel(logging.WARNING)
