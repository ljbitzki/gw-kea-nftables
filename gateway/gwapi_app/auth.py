import hmac
from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from .config import ADMIN_PASSWORD, ADMIN_USER

auth_bp = Blueprint("auth", __name__)


def is_authenticated():
    return session.get("authenticated") is True


def verify_credentials(username, password):
    return hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASSWORD)


def has_valid_basic_auth():
    auth = request.authorization
    if not auth:
        return False
    return verify_credentials(auth.username or "", auth.password or "")


def _safe_next_url(value):
    if not value:
        return url_for("web.firewall_ui")
    parsed = urlparse(value)
    if parsed.netloc or parsed.scheme:
        return url_for("web.firewall_ui")
    return value


def require_auth_for_request():
    if request.endpoint in {"auth.login", "auth.logout", "static"}:
        return None
    if not request.endpoint or not request.endpoint.startswith(("web.", "firewall.", "dhcp.")):
        return None
    if is_authenticated() or has_valid_basic_auth():
        return None

    wants_json = request.path == "/health" or request.path.startswith(("/firewall", "/dhcp"))
    if wants_json:
        return jsonify({"error": "autenticação requerida"}), 401

    return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))


@auth_bp.get("/login")
def login():
    if is_authenticated():
        return redirect(_safe_next_url(request.args.get("next")))
    return render_template("login.html", next_url=_safe_next_url(request.args.get("next")), error=None)


@auth_bp.post("/login")
def login_post():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    next_url = _safe_next_url(request.form.get("next"))

    if verify_credentials(username, password):
        session.clear()
        session["authenticated"] = True
        session["username"] = username
        return redirect(next_url)

    return render_template("login.html", next_url=next_url, error="Usuário ou senha inválidos"), 401


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
