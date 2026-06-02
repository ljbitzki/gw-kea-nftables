from flask import Flask

from .auth import auth_bp, require_auth_for_request
from .config import FLASK_SECRET_KEY
from .dhcp import dhcp_bp
from .firewall import firewall_bp
from .logging_config import configure_logging, log_request_finished, mark_request_start
from .web import web_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY
    configure_logging(app)
    app.before_request(mark_request_start)
    app.before_request(require_auth_for_request)
    app.after_request(log_request_finished)
    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(firewall_bp)
    app.register_blueprint(dhcp_bp)
    return app
