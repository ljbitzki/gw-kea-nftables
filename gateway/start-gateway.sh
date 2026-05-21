#!/usr/bin/env bash
set -euo pipefail

LAN_IP="${LAN_IP:-10.88.0.1}"
LAN_CIDR="${LAN_CIDR:-10.88.0.0/24}"
DHCP_POOL_START="${DHCP_POOL_START:-10.88.0.100}"
DHCP_POOL_END="${DHCP_POOL_END:-10.88.0.200}"
DHCP_DNS="${DHCP_DNS:-1.1.1.1, 8.8.8.8}"
DHCP_DOMAIN="${DHCP_DOMAIN:-lab.local}"
KEA_CA_PORT="${KEA_CA_PORT:-8000}"
FW_API_PORT="${FW_API_PORT:-8080}"

mkdir -p /run/kea /var/lib/kea /var/log/kea /etc/kea /etc/gwapi
chmod 0750 /run/kea || true

LAN_IF="$(ip -o -4 addr show | awk -v ip="${LAN_IP}" '$4 ~ "^" ip "/" {print $2; exit}')"
WAN_IF="$(ip route show default | awk '/default/ {print $5; exit}')"

if [[ -z "${LAN_IF}" ]]; then
  echo "ERRO: não consegui encontrar a interface LAN com IP ${LAN_IP}." >&2
  ip -o -4 addr show >&2
  exit 1
fi

if [[ -z "${WAN_IF}" ]]; then
  echo "ERRO: não consegui encontrar a interface WAN/default route." >&2
  ip route >&2
  exit 1
fi

export LAN_IF WAN_IF LAN_IP LAN_CIDR FW_API_PORT

echo "[gw] WAN_IF=${WAN_IF}; LAN_IF=${LAN_IF}; LAN_IP=${LAN_IP}; LAN_CIDR=${LAN_CIDR}"

echo 1 > /proc/sys/net/ipv4/ip_forward

cat > /etc/kea/kea-dhcp4.conf <<EOF_KEA4
{
  "Dhcp4": {
    "interfaces-config": {
      "interfaces": [ "${LAN_IF}" ]
    },
    "control-socket": {
      "socket-type": "unix",
      "socket-name": "/run/kea/kea4-ctrl-socket"
    },
    "lease-database": {
      "type": "memfile",
      "persist": true,
      "name": "/var/lib/kea/kea-leases4.csv",
      "lfc-interval": 3600
    },
    "valid-lifetime": 600,
    "renew-timer": 300,
    "rebind-timer": 500,
    "subnet4": [
      {
        "id": 1,
        "subnet": "${LAN_CIDR}",
        "pools": [
          { "pool": "${DHCP_POOL_START} - ${DHCP_POOL_END}" }
        ],
        "option-data": [
          { "name": "routers", "data": "${LAN_IP}" },
          { "name": "domain-name-servers", "data": "${DHCP_DNS}" },
          { "name": "domain-name", "data": "${DHCP_DOMAIN}" }
        ]
      }
    ],
    "loggers": [
      {
        "name": "kea-dhcp4",
        "severity": "INFO",
        "output_options": [ { "output": "stdout" } ]
      }
    ]
  }
}
EOF_KEA4

cat > /etc/kea/kea-ctrl-agent.conf <<EOF_CA
{
  "Control-agent": {
    "http-host": "0.0.0.0",
    "http-port": ${KEA_CA_PORT},
    "control-sockets": {
      "dhcp4": {
        "socket-type": "unix",
        "socket-name": "/run/kea/kea4-ctrl-socket"
      }
    },
    "loggers": [
      {
        "name": "kea-ctrl-agent",
        "severity": "INFO",
        "output_options": [ { "output": "stdout" } ]
      }
    ]
  }
}
EOF_CA

if [[ ! -f /etc/gwapi/firewall_state.json ]]; then
  cat > /etc/gwapi/firewall_state.json <<'EOF_FWSTATE'
{
  "default_policy": "drop",
  "rules": [
    { "id": "allow-dns-udp", "action": "allow", "proto": "udp", "dport": 53, "description": "Permite DNS UDP" },
    { "id": "allow-dns-tcp", "action": "allow", "proto": "tcp", "dport": 53, "description": "Permite DNS TCP" },
    { "id": "allow-http", "action": "allow", "proto": "tcp", "dport": 80, "description": "Permite HTTP" },
    { "id": "allow-https", "action": "allow", "proto": "tcp", "dport": 443, "description": "Permite HTTPS" },
    { "id": "allow-icmp", "action": "allow", "proto": "icmp", "description": "Permite ping" }
  ]
}
EOF_FWSTATE
fi

cleanup() {
  echo "[gw] encerrando serviços..."
  jobs -p | xargs -r kill || true
}
trap cleanup EXIT INT TERM

# Aplica nftables antes de subir os serviços.
python3 /opt/gwapi/app.py --apply-once

kea-dhcp4 -c /etc/kea/kea-dhcp4.conf &
sleep 1
kea-ctrl-agent -c /etc/kea/kea-ctrl-agent.conf &

python3 /opt/gwapi/app.py
