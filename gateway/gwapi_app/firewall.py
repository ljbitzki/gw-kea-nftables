import ipaddress
import json
import subprocess
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

from .config import LAN_CIDR, LAN_IF, STATE_FILE, WAN_IF

firewall_bp = Blueprint("firewall", __name__)


def _run(cmd):
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def load_state():
    if not STATE_FILE.exists():
        return {"default_policy": "drop", "rules": []}
    with STATE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("default_policy", "drop")
    data.setdefault("rules", [])
    return data


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(STATE_FILE)


def validate_rule(rule, assign_id=True):
    action = str(rule.get("action", "")).lower()
    proto = str(rule.get("proto", "all")).lower()

    if action not in {"allow", "drop"}:
        raise ValueError("action deve ser 'allow' ou 'drop'")
    if proto not in {"tcp", "udp", "icmp", "all"}:
        raise ValueError("proto deve ser 'tcp', 'udp', 'icmp' ou 'all'")

    normalized = {
        "id": str(rule.get("id") or uuid.uuid4()) if assign_id else str(rule.get("id", "")),
        "action": action,
        "proto": proto,
    }

    if "description" in rule:
        normalized["description"] = str(rule["description"])

    if rule.get("src"):
        try:
            normalized["src"] = str(ipaddress.ip_network(str(rule["src"]), strict=False))
        except ValueError as exc:
            raise ValueError(f"src inválido: {exc}") from exc

    if rule.get("dst"):
        try:
            normalized["dst"] = str(ipaddress.ip_network(str(rule["dst"]), strict=False))
        except ValueError as exc:
            raise ValueError(f"dst inválido: {exc}") from exc

    if "dport" in rule and rule["dport"] is not None:
        if proto not in {"tcp", "udp"}:
            raise ValueError("dport só é aceito com proto tcp ou udp")
        try:
            dport = int(rule["dport"])
        except (TypeError, ValueError) as exc:
            raise ValueError("dport deve ser número inteiro") from exc
        if not (1 <= dport <= 65535):
            raise ValueError("dport deve estar entre 1 e 65535")
        normalized["dport"] = dport

    return normalized


def rule_to_nft(rule):
    verdict = "accept" if rule["action"] == "allow" else "drop"
    expr = []

    src = rule.get("src")
    if src:
        expr.append(f"ip saddr {src}")

    dst = rule.get("dst")
    if dst:
        expr.append(f"ip daddr {dst}")

    proto = rule.get("proto", "all")
    if proto == "tcp":
        expr.append("meta l4proto tcp")
        if "dport" in rule:
            expr.append(f"tcp dport {rule['dport']}")
    elif proto == "udp":
        expr.append("meta l4proto udp")
        if "dport" in rule:
            expr.append(f"udp dport {rule['dport']}")
    elif proto == "icmp":
        expr.append("ip protocol icmp")

    comment = rule.get("description") or rule.get("id")
    safe_comment = str(comment).replace('"', "'")[:120]
    expr.append(f"counter {verdict} comment \"{safe_comment}\"")
    return "        " + " ".join(expr)


def build_ruleset(state):
    default_policy = state.get("default_policy", "drop")
    if default_policy not in {"allow", "drop"}:
        raise ValueError("default_policy deve ser 'allow' ou 'drop'")

    default_verdict = "accept" if default_policy == "allow" else "drop"
    rules = [rule_to_nft(validate_rule(r, assign_id=False)) for r in state.get("rules", [])]
    rules_text = "\n".join(rules) if rules else "        # sem regras explícitas"

    # Em laboratorio, a API fica aberta em 8000/8080. Em producao, reavaliar.
    return f"""
flush ruleset

table inet gw_filter {{
    chain input {{
        type filter hook input priority 0; policy drop;
        iifname "lo" accept
        ct state established,related accept
        iifname "{LAN_IF}" udp dport {{ 67, 68 }} accept comment "DHCP na LAN"
        tcp dport {{ 8000, 8080 }} accept comment "APIs de controle do laboratorio"
        ip protocol icmp accept comment "ICMP diagnostico"
    }}

    chain forward {{
        type filter hook forward priority 0; policy drop;
        ct state established,related accept
        iifname "{LAN_IF}" oifname "{WAN_IF}" jump lan_to_wan
    }}

    chain lan_to_wan {{
{rules_text}
        counter {default_verdict} comment "politica default LAN->WAN: {default_policy}"
    }}
}}

table ip gw_nat {{
    chain postrouting {{
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr {LAN_CIDR} oifname "{WAN_IF}" masquerade
    }}
}}
""".strip() + "\n"


def apply_rules():
    state = load_state()
    ruleset = build_ruleset(state)
    nft_file = Path("/tmp/gwapi-ruleset.nft")
    nft_file.write_text(ruleset, encoding="utf-8")
    _run(["nft", "-f", str(nft_file)])
    return state


@firewall_bp.get("/health")
def health():
    from .config import KEA_CA_URL

    return jsonify({
        "status": "ok",
        "lan_if": LAN_IF,
        "wan_if": WAN_IF,
        "lan_cidr": LAN_CIDR,
        "kea_ca_url": KEA_CA_URL,
    })


@firewall_bp.get("/firewall")
def firewall_get():
    return jsonify(load_state())


@firewall_bp.post("/firewall/apply")
def firewall_apply():
    try:
        state = apply_rules()
        return jsonify({"applied": True, "state": state})
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        return jsonify({"applied": False, "error": str(exc)}), 400


@firewall_bp.put("/firewall/default")
def firewall_default():
    body = request.get_json(force=True, silent=True) or {}
    policy = str(body.get("policy", "")).lower()
    if policy not in {"allow", "drop"}:
        return jsonify({"error": "policy deve ser 'allow' ou 'drop'"}), 400
    state = load_state()
    state["default_policy"] = policy
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state())


@firewall_bp.post("/firewall/rules")
def firewall_rule_add():
    body = request.get_json(force=True, silent=True) or {}
    try:
        rule = validate_rule(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    position = str(body.get("position", "last")).lower()
    if position in {"first", "top"}:
        state["rules"].insert(0, rule)
    else:
        state["rules"].append(rule)
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(rule), 201


@firewall_bp.get("/firewall/rules/<rule_id>")
def firewall_rule_get(rule_id):
    state = load_state()
    for rule in state["rules"]:
        if str(rule.get("id")) == rule_id:
            return jsonify(rule)
    return jsonify({"error": "regra não encontrada"}), 404


@firewall_bp.put("/firewall/rules/<rule_id>")
def firewall_rule_update(rule_id):
    body = request.get_json(force=True, silent=True) or {}
    body.setdefault("id", rule_id)

    try:
        rule = validate_rule(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    for index, current in enumerate(state["rules"]):
        if str(current.get("id")) == rule_id:
            state["rules"][index] = rule
            save_state(state)
            try:
                apply_rules()
            except Exception as exc:  # noqa: BLE001
                return jsonify({"error": str(exc)}), 400
            return jsonify(rule)

    return jsonify({"error": "regra não encontrada"}), 404


@firewall_bp.delete("/firewall/rules/<rule_id>")
def firewall_rule_delete(rule_id):
    state = load_state()
    before = len(state["rules"])
    state["rules"] = [r for r in state["rules"] if str(r.get("id")) != rule_id]
    if len(state["rules"]) == before:
        return jsonify({"error": "regra não encontrada"}), 404
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state())
