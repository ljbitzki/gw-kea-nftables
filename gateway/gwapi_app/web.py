from flask import Blueprint, render_template

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def firewall_ui():
    return render_template("firewall.html")
