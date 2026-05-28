from flask import Blueprint, jsonify, request

from .dhcp_service import (
    apply_reservations,
    dhcp_summary,
    get_kea_dhcp4_config,
    kea_command,
    load_reservation_state,
    read_leases,
    save_reservation_state,
    validate_reservation,
)

dhcp_bp = Blueprint("dhcp", __name__)


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
    try:
        config = get_kea_dhcp4_config()
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        return jsonify({"error": str(exc)}), 502
    return jsonify(config)


@dhcp_bp.get("/dhcp/summary")
def dhcp_summary_get():
    try:
        return jsonify(dhcp_summary())
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        return jsonify({"error": str(exc)}), 502


@dhcp_bp.get("/dhcp/leases")
def dhcp_leases_get():
    return jsonify(read_leases())


@dhcp_bp.get("/dhcp/reservations")
def dhcp_reservations_get():
    return jsonify(load_reservation_state()["reservations"])


@dhcp_bp.post("/dhcp/reservations")
def dhcp_reservation_add():
    body = request.get_json(force=True, silent=True) or {}
    try:
        reservation = validate_reservation(body, assign_id=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_reservation_state()
    for current in state["reservations"]:
        if current["ip_address"] == reservation["ip_address"]:
            return jsonify({"error": "já existe reservation para este IP"}), 409
        if current["hw_address"] == reservation["hw_address"]:
            return jsonify({"error": "já existe reservation para este MAC"}), 409

    state["reservations"].append(reservation)
    save_reservation_state(state)
    try:
        apply_reservations()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(reservation), 201


@dhcp_bp.put("/dhcp/reservations/<reservation_id>")
def dhcp_reservation_update(reservation_id):
    body = request.get_json(force=True, silent=True) or {}
    body["id"] = reservation_id

    try:
        reservation = validate_reservation(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    state = load_reservation_state()
    for current in state["reservations"]:
        if current["id"] == reservation_id:
            continue
        if current["ip_address"] == reservation["ip_address"]:
            return jsonify({"error": "já existe reservation para este IP"}), 409
        if current["hw_address"] == reservation["hw_address"]:
            return jsonify({"error": "já existe reservation para este MAC"}), 409

    for index, current in enumerate(state["reservations"]):
        if current["id"] == reservation_id:
            state["reservations"][index] = reservation
            save_reservation_state(state)
            try:
                apply_reservations()
            except Exception as exc:  # noqa: BLE001
                return jsonify({"error": str(exc)}), 400
            return jsonify(reservation)

    return jsonify({"error": "reservation não encontrada"}), 404


@dhcp_bp.delete("/dhcp/reservations/<reservation_id>")
def dhcp_reservation_delete(reservation_id):
    state = load_reservation_state()
    before = len(state["reservations"])
    state["reservations"] = [item for item in state["reservations"] if item["id"] != reservation_id]
    if len(state["reservations"]) == before:
        return jsonify({"error": "reservation não encontrada"}), 404

    save_reservation_state(state)
    try:
        apply_reservations()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(load_reservation_state()["reservations"])


@dhcp_bp.post("/dhcp/apply")
def dhcp_apply():
    try:
        return jsonify(apply_reservations())
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        return jsonify({"applied": False, "error": str(exc)}), 400
