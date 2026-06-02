#!/usr/bin/env bash
# Cliente de exemplo, para demonstrar recebimento de ip via kea do conainer
set -euo pipefail

IFACE="${IFACE:-eth0}"

dhclient -r "${IFACE}" >/dev/null 2>&1 || true
ip addr flush dev "${IFACE}" || true
ip route flush dev "${IFACE}" || true
ip link set "${IFACE}" up

echo "[client] interface ${IFACE}; mac=$(cat "/sys/class/net/${IFACE}/address")"
echo "[client] solicitando DHCP em ${IFACE}..."
dhclient -4 -v "${IFACE}"

echo "[client] endereços:"
ip -4 addr show dev "${IFACE}"
echo "[client] rotas:"
ip route

tail -f /dev/null
