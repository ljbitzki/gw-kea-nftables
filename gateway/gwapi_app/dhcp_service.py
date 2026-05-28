import csv
import ipaddress
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from .config import DHCP_RESERVATIONS_FILE, KEA_CA_URL, KEA_LEASES_FILE

MAC_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


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


def load_reservation_state():
    if not DHCP_RESERVATIONS_FILE.exists():
        return {"reservations": []}
    with DHCP_RESERVATIONS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("reservations", [])
    data["reservations"] = [validate_reservation(item) for item in data["reservations"]]
    return data


def save_reservation_state(state):
    state.setdefault("reservations", [])
    state["reservations"] = [validate_reservation(item) for item in state["reservations"]]
    DHCP_RESERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DHCP_RESERVATIONS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(DHCP_RESERVATIONS_FILE)


def normalize_mac(value):
    normalized = str(value or "").strip().lower()
    if not MAC_RE.match(normalized):
        raise ValueError("hw_address deve estar no formato aa:bb:cc:dd:ee:ff")
    return normalized


def normalize_ip(value):
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError as exc:
        raise ValueError(f"ip_address inválido: {exc}") from exc


def validate_reservation(data, assign_id=False):
    reservation_id = str(data.get("id") or uuid.uuid4()) if assign_id else str(data.get("id", ""))
    if not reservation_id:
        reservation_id = str(uuid.uuid4())

    try:
        subnet_id = int(data.get("subnet_id", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("subnet_id deve ser número inteiro") from exc
    if subnet_id < 1:
        raise ValueError("subnet_id deve ser maior que zero")

    reservation = {
        "id": reservation_id,
        "subnet_id": subnet_id,
        "hw_address": normalize_mac(data.get("hw_address") or data.get("hw-address")),
        "ip_address": normalize_ip(data.get("ip_address") or data.get("ip-address")),
    }

    hostname = str(data.get("hostname", "")).strip()
    if hostname:
        reservation["hostname"] = hostname

    return reservation


def reservation_to_kea(reservation):
    payload = {
        "hw-address": reservation["hw_address"],
        "ip-address": reservation["ip_address"],
        "user-context": {
            "gwapi": {
                "reservation_id": reservation["id"],
            },
        },
    }
    if reservation.get("hostname"):
        payload["hostname"] = reservation["hostname"]
    return payload


def get_kea_dhcp4_config():
    result, status = kea_command({"command": "config-get", "service": ["dhcp4"]})
    if status >= 400:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    try:
        return result[0]["arguments"]["Dhcp4"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("resposta inesperada do Kea em config-get") from exc


def set_kea_dhcp4_config(dhcp4_config):
    result, status = kea_command({
        "command": "config-set",
        "service": ["dhcp4"],
        "arguments": {"Dhcp4": dhcp4_config},
    })
    if status >= 400:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def is_managed_reservation(reservation):
    context = reservation.get("user-context", {})
    return bool(context.get("gwapi", {}).get("reservation_id"))


def apply_reservations(retries=0, delay=1):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return _apply_reservations_once()
        except Exception as exc:  # noqa: BLE001 - tentativa de boot em laboratório
            last_error = exc
            if attempt < retries:
                time.sleep(delay)
    raise last_error


def _apply_reservations_once():
    state = load_reservation_state()
    reservations = state["reservations"]
    config = get_kea_dhcp4_config()

    by_subnet = {}
    for reservation in reservations:
        by_subnet.setdefault(reservation["subnet_id"], []).append(reservation)

    for subnet in config.get("subnet4", []):
        subnet_id = int(subnet.get("id", 0))
        managed = by_subnet.get(subnet_id, [])
        managed_ips = {item["ip_address"] for item in managed}
        managed_macs = {item["hw_address"] for item in managed}

        current = subnet.get("reservations", []) or []
        preserved = [
            item for item in current
            if not is_managed_reservation(item)
            and item.get("ip-address") not in managed_ips
            and str(item.get("hw-address", "")).lower() not in managed_macs
        ]
        subnet["reservations"] = preserved + [reservation_to_kea(item) for item in managed]

    result = set_kea_dhcp4_config(config)
    return {
        "applied": True,
        "result": result,
        "reservations": reservations,
    }


def _timestamp_to_iso(value):
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def read_leases():
    if not KEA_LEASES_FILE.exists():
        return []

    leases = []
    with KEA_LEASES_FILE.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("address"):
                continue
            leases.append({
                "address": row.get("address", ""),
                "hw_address": row.get("hwaddr", ""),
                "client_id": row.get("client_id", ""),
                "valid_lifetime": _safe_int(row.get("valid_lifetime")),
                "expire": _safe_int(row.get("expire")),
                "expire_at": _timestamp_to_iso(row.get("expire")),
                "subnet_id": _safe_int(row.get("subnet_id")),
                "hostname": row.get("hostname", ""),
                "state": _safe_int(row.get("state")),
                "state_label": lease_state_label(row.get("state")),
            })
    return leases


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def lease_state_label(value):
    labels = {
        "0": "default",
        "1": "declined",
        "2": "expired-reclaimed",
    }
    return labels.get(str(value), str(value or ""))


def summarize_config(dhcp4_config):
    subnets = []
    for subnet in dhcp4_config.get("subnet4", []):
        option_data = subnet.get("option-data", []) or []
        subnets.append({
            "id": subnet.get("id"),
            "subnet": subnet.get("subnet"),
            "pools": [pool.get("pool") for pool in subnet.get("pools", []) if pool.get("pool")],
            "options": {
                item.get("name"): item.get("data")
                for item in option_data
                if item.get("name")
            },
            "reservations_count": len(subnet.get("reservations", []) or []),
        })
    return {
        "valid_lifetime": dhcp4_config.get("valid-lifetime"),
        "renew_timer": dhcp4_config.get("renew-timer"),
        "rebind_timer": dhcp4_config.get("rebind-timer"),
        "subnets": subnets,
    }


def dhcp_summary():
    status, status_code = kea_command({"command": "status-get", "service": ["dhcp4"]})
    config = get_kea_dhcp4_config()
    leases = read_leases()
    reservations = load_reservation_state()["reservations"]
    return {
        "status_code": status_code,
        "status": status,
        "config": summarize_config(config),
        "leases_count": len(leases),
        "reservations_count": len(reservations),
    }
