import ipaddress
import json
import re
import subprocess
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

from .config import LAN_CIDR, LAN_IF, STATE_FILE, WAN_IF

firewall_bp = Blueprint("firewall", __name__)

GROUP_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
DEFAULT_GROUPS = {
    "manual_blocked": {
        "description": "Manualmente bloqueados",
        "members": [],
    },
    "manual_allowed": {
        "description": "Manualmente liberados",
        "members": [],
    },
}
DEFAULT_GROUP_RULES = [
    {
        "id": "drop-manual-blocked",
        "action": "drop",
        "proto": "all",
        "src_group": "manual_blocked",
        "description": "Bloqueia hosts manualmente bloqueados",
        "system": True,
    },
    {
        "id": "allow-manual-allowed",
        "action": "allow",
        "proto": "all",
        "src_group": "manual_allowed",
        "description": "Libera hosts manualmente liberados",
        "system": True,
    },
]


def _run(cmd):
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def validate_group_name(name):
    normalized = str(name or "").strip()
    if not GROUP_NAME_RE.match(normalized):
        raise ValueError("nome do grupo deve começar com letra/_ e conter apenas letras, números e _")
    return normalized


def normalize_network(value):
    try:
        return str(ipaddress.ip_network(str(value), strict=False))
    except ValueError as exc:
        raise ValueError(f"membro inválido: {exc}") from exc


def normalize_group(group, group_id=None):
    if group_id is not None:
        group_id = validate_group_name(group_id)

    members = []
    seen = set()
    for member in group.get("members", []):
        normalized_member = normalize_network(member)
        if normalized_member not in seen:
            members.append(normalized_member)
            seen.add(normalized_member)

    normalized = {
        "description": str(group.get("description", group_id or "")),
        "members": members,
    }
    if group.get("system"):
        normalized["system"] = True
    return normalized


def normalize_state(data):
    data.setdefault("default_policy", "drop")
    data.setdefault("rules", [])
    data.setdefault("groups", {})

    groups = {}
    for group_id, group in DEFAULT_GROUPS.items():
        stored_group = data["groups"].get(group_id, group)
        groups[group_id] = normalize_group({**group, **stored_group}, group_id)
        groups[group_id]["system"] = True

    for group_id, group in data["groups"].items():
        group_id = validate_group_name(group_id)
        if group_id in groups:
            continue
        groups[group_id] = normalize_group(group, group_id)

    data["groups"] = groups

    system_rules = []
    for rule in DEFAULT_GROUP_RULES:
        current = next((r for r in data["rules"] if str(r.get("id")) == rule["id"]), rule)
        system_rules.append({**current, **rule, "system": True})

    custom_rules = [rule for rule in data["rules"] if str(rule.get("id")) not in {r["id"] for r in DEFAULT_GROUP_RULES}]
    data["rules"] = system_rules + custom_rules
    return data


def load_state():
    if not STATE_FILE.exists():
        return normalize_state({"default_policy": "drop", "rules": [], "groups": {}})
    with STATE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return normalize_state(data)


def save_state(state):
    state = normalize_state(state)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(STATE_FILE)


def validate_rule(rule, groups=None, assign_id=True):
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
    if rule.get("system"):
        normalized["system"] = True

    src_group = str(rule.get("src_group", "")).strip()
    dst_group = str(rule.get("dst_group", "")).strip()
    if src_group and rule.get("src"):
        raise ValueError("src e src_group não podem ser usados juntos")
    if dst_group and rule.get("dst"):
        raise ValueError("dst e dst_group não podem ser usados juntos")

    if src_group:
        src_group = validate_group_name(src_group)
        if groups is not None and src_group not in groups:
            raise ValueError("src_group não encontrado")
        normalized["src_group"] = src_group

    if dst_group:
        dst_group = validate_group_name(dst_group)
        if groups is not None and dst_group not in groups:
            raise ValueError("dst_group não encontrado")
        normalized["dst_group"] = dst_group

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

    src_group = rule.get("src_group")
    if src_group:
        expr.append(f"ip saddr @{src_group}")

    dst = rule.get("dst")
    if dst:
        expr.append(f"ip daddr {dst}")

    dst_group = rule.get("dst_group")
    if dst_group:
        expr.append(f"ip daddr @{dst_group}")

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


def group_to_nft(group_id, group):
    lines = [
        f"    set {group_id} {{",
        "        type ipv4_addr",
        "        flags interval",
    ]
    members = group.get("members", [])
    if members:
        lines.append(f"        elements = {{ {', '.join(members)} }}")
    lines.append("    }")
    return "\n".join(lines)


def build_ruleset(state):
    state = normalize_state(state)
    default_policy = state.get("default_policy", "drop")
    if default_policy not in {"allow", "drop"}:
        raise ValueError("default_policy deve ser 'allow' ou 'drop'")

    default_verdict = "accept" if default_policy == "allow" else "drop"
    groups = state.get("groups", {})
    sets_text = "\n\n".join(group_to_nft(group_id, group) for group_id, group in groups.items())
    rules = [rule_to_nft(validate_rule(r, groups=groups, assign_id=False)) for r in state.get("rules", [])]
    rules_text = "\n".join(rules) if rules else "        # sem regras explícitas"

    # Em laboratorio, a API fica aberta em 8000/8080. Em producao, reavaliar.
    return f"""
flush ruleset

table inet gw_filter {{
{sets_text}

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
    state = load_state()
    try:
        rule = validate_rule(body, groups=state["groups"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

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
    state = load_state()

    try:
        rule = validate_rule(body, groups=state["groups"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    for index, current in enumerate(state["rules"]):
        if str(current.get("id")) == rule_id:
            if current.get("system"):
                return jsonify({"error": "regra de sistema não pode ser editada"}), 400
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
    for rule in state["rules"]:
        if str(rule.get("id")) == rule_id and rule.get("system"):
            return jsonify({"error": "regra de sistema não pode ser removida"}), 400
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


@firewall_bp.get("/firewall/groups")
def firewall_groups_get():
    return jsonify(load_state().get("groups", {}))


@firewall_bp.get("/firewall/groups/<group_id>")
def firewall_group_get(group_id):
    try:
        group_id = validate_group_name(group_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    group = load_state()["groups"].get(group_id)
    if not group:
        return jsonify({"error": "grupo não encontrado"}), 404
    return jsonify(group)


@firewall_bp.post("/firewall/groups")
def firewall_group_add():
    body = request.get_json(force=True, silent=True) or {}
    try:
        group_id = validate_group_name(body.get("id"))
        group = normalize_group(body, group_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    if group_id in state["groups"]:
        return jsonify({"error": "grupo já existe"}), 409

    state["groups"][group_id] = group
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify({group_id: load_state()["groups"][group_id]}), 201


@firewall_bp.put("/firewall/groups/<group_id>")
def firewall_group_update(group_id):
    try:
        group_id = validate_group_name(group_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    body = request.get_json(force=True, silent=True) or {}
    state = load_state()
    if group_id not in state["groups"]:
        return jsonify({"error": "grupo não encontrado"}), 404

    current = state["groups"][group_id]
    if current.get("system"):
        body["system"] = True
    try:
        state["groups"][group_id] = normalize_group({**current, **body}, group_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state()["groups"][group_id])


@firewall_bp.delete("/firewall/groups/<group_id>")
def firewall_group_delete(group_id):
    try:
        group_id = validate_group_name(group_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    group = state["groups"].get(group_id)
    if not group:
        return jsonify({"error": "grupo não encontrado"}), 404
    if group.get("system"):
        return jsonify({"error": "grupo de sistema não pode ser removido"}), 400
    for rule in state["rules"]:
        if rule.get("src_group") == group_id or rule.get("dst_group") == group_id:
            return jsonify({"error": "grupo está em uso por regra"}), 400

    del state["groups"][group_id]
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state()["groups"])


@firewall_bp.post("/firewall/groups/<group_id>/members")
def firewall_group_member_add(group_id):
    try:
        group_id = validate_group_name(group_id)
        member = normalize_network((request.get_json(force=True, silent=True) or {}).get("member"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    group = state["groups"].get(group_id)
    if not group:
        return jsonify({"error": "grupo não encontrado"}), 404

    if member not in group["members"]:
        group["members"].append(member)
    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state()["groups"][group_id])


@firewall_bp.delete("/firewall/groups/<group_id>/members")
def firewall_group_member_delete(group_id):
    try:
        group_id = validate_group_name(group_id)
        member = normalize_network((request.get_json(force=True, silent=True) or {}).get("member"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_state()
    group = state["groups"].get(group_id)
    if not group:
        return jsonify({"error": "grupo não encontrado"}), 404

    before = len(group["members"])
    group["members"] = [item for item in group["members"] if item != member]
    if len(group["members"]) == before:
        return jsonify({"error": "membro não encontrado"}), 404

    save_state(state)
    try:
        apply_rules()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_state()["groups"][group_id])
