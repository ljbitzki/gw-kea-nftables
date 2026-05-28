from flask import Flask

from .dhcp import dhcp_bp
from .firewall import firewall_bp
from .web import web_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(web_bp)
    app.register_blueprint(firewall_bp)
    app.register_blueprint(dhcp_bp)
    return app
