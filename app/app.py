import atexit
import logging
import os
import signal

from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask
from flask_cors import CORS
from logging_config import configure_logging
from middleware import RequestIDMiddleware
from autologin import load_settings, validate
from mt5_connection import MT5Connection
from routes.account import account_bp
from routes.data import data_bp
from routes.error import error_bp
from routes.health import health_bp
from routes.history import history_bp
from routes.order import order_bp
from routes.position import position_bp
from routes.symbol import symbol_bp
from swagger import swagger_config
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, expose_headers=["X-Request-ID"])
RequestIDMiddleware(app)

swagger = Swagger(app, config=swagger_config)

app.register_blueprint(health_bp)
app.register_blueprint(symbol_bp)
app.register_blueprint(data_bp)
app.register_blueprint(position_bp)
app.register_blueprint(order_bp)
app.register_blueprint(account_bp)
app.register_blueprint(history_bp)
app.register_blueprint(error_bp)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


def shutdown_handler(signum=None, frame=None):
    logger.info("Received shutdown signal, closing MT5 connection")
    conn = MT5Connection.get_instance()
    conn.shutdown()


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)
atexit.register(shutdown_handler)

try:
    validate(load_settings(os.environ))
except ValueError as e:
    logger.error(f"Invalid env-login config: {e}")

conn = MT5Connection.get_instance()
if not conn.initialize():
    logger.error("Failed to initialize MT5, but starting server anyway")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("MT5_API_PORT", 5001)))

