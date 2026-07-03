"""Flask application factory and process lifecycle."""

import atexit
import logging
import os
import signal

from autologin import load_settings, validate
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask
from flask_cors import CORS
from logging_config import configure_logging
from metrics import metrics_bp
from middleware import RequestIDMiddleware
from mt5_connection import MT5Connection
from responses import install_response_envelope
from routes.account import account_bp
from routes.control import control_bp
from routes.data import data_bp
from routes.error import error_bp
from routes.health import health_bp
from routes.history import history_bp
from routes.order import order_bp
from routes.position import position_bp
from routes.symbol import symbol_bp
from security import install_security_hooks
from swagger import swagger_config
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Settings

logger = logging.getLogger(__name__)
_shutdown_registered = False


def create_app(start_mt5=True):
    """Build the WSGI app; tests may disable the external MT5 startup."""
    load_dotenv()
    configure_logging()
    settings = Settings.from_env()
    application = Flask(__name__)
    application.config["SETTINGS"] = settings

    if settings.cors_origins:
        CORS(
            application,
            resources={r"/*": {"origins": settings.cors_origins}},
            expose_headers=["X-Request-ID"],
        )
    RequestIDMiddleware(application)
    install_security_hooks(application)
    install_response_envelope(application)
    Swagger(application, config=swagger_config)

    for blueprint in (
        health_bp,
        symbol_bp,
        data_bp,
        position_bp,
        order_bp,
        account_bp,
        history_bp,
        error_bp,
        control_bp,
        metrics_bp,
    ):
        application.register_blueprint(blueprint)
    application.wsgi_app = ProxyFix(application.wsgi_app, x_proto=1, x_host=1)

    if start_mt5:
        _start_mt5()
        _register_shutdown_handlers()
    return application


def _start_mt5():
    try:
        validate(load_settings(os.environ))
    except ValueError as error:
        logger.error("Invalid env-login config: %s", error)
    connection = MT5Connection.get_instance()
    if not connection.initialize():
        logger.error("Failed to initialize MT5, but starting server anyway")


def shutdown_handler(signum=None, frame=None):
    logger.info("Received shutdown signal, closing MT5 connection")
    MT5Connection.get_instance().shutdown()


def _register_shutdown_handlers():
    global _shutdown_registered
    if _shutdown_registered:
        return
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    atexit.register(shutdown_handler)
    _shutdown_registered = True


if __name__ == "__main__":
    settings = Settings.from_env()
    create_app().run(host="0.0.0.0", port=settings.api_port)
