import logging

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
logger = logging.getLogger("gwapi")


def _service_label(value):
    if isinstance(value, list):
        return ",".join(value)
    return value or "-"


@dhcp_bp.post("/dhcp/kea")
def dhcp_kea_proxy():
    body = request.get_json(force=True, silent=True) or {}
    result, status = kea_command(body)
    logger.info(
        "dhcp_kea_proxy command=%s service=%s status=%s",
        body.get("command", "-"),
        _service_label(body.get("service")),
        status,
    )
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
        logger.exception("dhcp_config_get_failed error=%s", exc)
        return jsonify({"error": str(exc)}), 502
    return jsonify(config)


@dhcp_bp.get("/dhcp/summary")
def dhcp_summary_get():
    try:
        return jsonify(dhcp_summary())
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        logger.exception("dhcp_summary_failed error=%s", exc)
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
        logger.exception(
            "dhcp_reservation_add_failed id=%s ip=%s hw=%s error=%s",
            reservation["id"],
            reservation["ip_address"],
            reservation["hw_address"],
            exc,
        )
        return jsonify({"error": str(exc)}), 400
    logger.info(
        "dhcp_reservation_added id=%s ip=%s hw=%s hostname=%s",
        reservation["id"],
        reservation["ip_address"],
        reservation["hw_address"],
        reservation.get("hostname", "-"),
    )
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
                logger.exception(
                    "dhcp_reservation_update_failed id=%s ip=%s hw=%s error=%s",
                    reservation_id,
                    reservation["ip_address"],
                    reservation["hw_address"],
                    exc,
                )
                return jsonify({"error": str(exc)}), 400
            logger.info(
                "dhcp_reservation_updated id=%s ip=%s hw=%s hostname=%s",
                reservation_id,
                reservation["ip_address"],
                reservation["hw_address"],
                reservation.get("hostname", "-"),
            )
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
        logger.exception("dhcp_reservation_delete_failed id=%s error=%s", reservation_id, exc)
        return jsonify({"error": str(exc)}), 400
    logger.info("dhcp_reservation_deleted id=%s", reservation_id)
    return jsonify(load_reservation_state()["reservations"])


@dhcp_bp.post("/dhcp/apply")
def dhcp_apply():
    try:
        result = apply_reservations()
        logger.info("dhcp_reservations_applied reservations=%s", len(result.get("reservations", [])))
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        logger.exception("dhcp_reservations_apply_failed error=%s", exc)
        return jsonify({"applied": False, "error": str(exc)}), 400
