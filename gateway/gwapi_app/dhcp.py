import json
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request

from .config import KEA_CA_URL

dhcp_bp = Blueprint("dhcp", __name__)


def kea_command(payload):
    encoded = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        KEA_CA_URL,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw), resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"error": raw}
        return body, exc.code
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        return {"error": str(exc)}, 502


@dhcp_bp.post("/dhcp/kea")
def dhcp_kea_proxy():
    body = request.get_json(force=True, silent=True) or {}
    result, status = kea_command(body)
    return jsonify(result), status


@dhcp_bp.get("/dhcp/status")
def dhcp_status():
    result, status = kea_command({"command": "status-get", "service": ["dhcp4"]})
    return jsonify(result), status


@dhcp_bp.get("/dhcp/config")
def dhcp_config():
    result, status = kea_command({"command": "config-get", "service": ["dhcp4"]})
    return jsonify(result), status
