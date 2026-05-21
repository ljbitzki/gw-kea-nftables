#!/usr/bin/env python3
"""
Configura o arquivo .env para o protótipo container gateway + Kea + firewall.

Uso típico:
  python3 reconfigure.py
  docker compose --env-file .env up -d --build

  O docker compose também já lê automaticamente um arquivo chamado .env no mesmo diretório do docker-compose.yml.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Callable

ENV_FILE = Path(".env")

DEFAULTS: dict[str, str] = {
    "LAN_IP": "10.88.0.1",
    "LAN_CIDR": "10.88.0.0/24",
    "LAN_DOCKER_GATEWAY": "10.88.0.254",
    "LAN_DOCKER_IP_RANGE": "10.88.0.240/28",
    "DHCP_POOL_START": "10.88.0.100",
    "DHCP_POOL_END": "10.88.0.200",
    "DHCP_DNS": "1.1.1.1, 8.8.8.8",
    "DHCP_DOMAIN": "lab.local",
    "FW_API_PORT": "8080",
    "KEA_CA_PORT": "8000",
    "FW_API_HOST_PORT": "18080",
    "KEA_CA_HOST_PORT": "18000",
}

LABELS: dict[str, str] = {
    "LAN_IP": "IP fixo do gateway na LAN",
    "LAN_CIDR": "Rede/CIDR da LAN",
    "LAN_DOCKER_GATEWAY": "Gateway interno da bridge Docker",
    "LAN_DOCKER_IP_RANGE": "Faixa IPAM Docker temporária",
    "DHCP_POOL_START": "Início do pool DHCP Kea",
    "DHCP_POOL_END": "Fim do pool DHCP Kea",
    "DHCP_DNS": "Servidores DNS entregues por DHCP",
    "DHCP_DOMAIN": "Domínio entregue por DHCP",
    "FW_API_PORT": "Porta interna da API do firewall no gw",
    "KEA_CA_PORT": "Porta interna do Kea Control Agent no gw",
    "FW_API_HOST_PORT": "Porta publicada no host para a API do firewall",
    "KEA_CA_HOST_PORT": "Porta publicada no host para o Kea Control Agent",
}


def read_env(path: Path) -> dict[str, str]:
    data = DEFAULTS.copy()
    if not path.exists():
        return data

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in DEFAULTS:
            data[key] = value
    return data


def write_env(path: Path, cfg: dict[str, str]) -> None:
    lines = [
        "# Arquivo gerado por configure-gw-env.py",
        "# O docker compose lê este arquivo automaticamente quando ele está no mesmo diretório do docker-compose.yml.",
        "",
    ]
    for key in DEFAULTS:
        lines.append(f"# {LABELS[key]}")
        lines.append(f"{key}={cfg[key]}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[S/n]" if default else "[s/N]"
    while True:
        value = input(f"{prompt} {suffix}: ").strip().lower()
        if not value:
            return default
        if value in {"s", "sim", "y", "yes"}:
            return True
        if value in {"n", "nao", "não", "no"}:
            return False
        print("Resposta inválida. Digite 's' ou 'n'.")


def parse_ipv4(value: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise ValueError(f"'{value}' não é um IPv4 válido") from exc


def parse_net(value: str) -> ipaddress.IPv4Network:
    try:
        return ipaddress.IPv4Network(value, strict=True)
    except ValueError as exc:
        raise ValueError(f"'{value}' não é uma rede CIDR válida. Exemplo: 10.88.0.0/24") from exc


def parse_port(value: str) -> int:
    if not value.isdigit():
        raise ValueError("a porta deve ser numérica")
    port = int(value)
    if not (1 <= port <= 65535):
        raise ValueError("a porta deve estar entre 1 e 65535")
    return port


def parse_dns(value: str) -> list[ipaddress.IPv4Address]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("informe ao menos um DNS")
    return [parse_ipv4(part) for part in parts]


def parse_domain(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("domínio não pode ficar vazio")
    pattern = r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
    if not re.match(pattern, value):
        raise ValueError("domínio inválido. Exemplo válido: lab.local")
    return value


def validate_all(cfg: dict[str, str]) -> None:
    lan = parse_net(cfg["LAN_CIDR"])
    lan_ip = parse_ipv4(cfg["LAN_IP"])
    docker_gw = parse_ipv4(cfg["LAN_DOCKER_GATEWAY"])
    docker_range = parse_net(cfg["LAN_DOCKER_IP_RANGE"])
    pool_start = parse_ipv4(cfg["DHCP_POOL_START"])
    pool_end = parse_ipv4(cfg["DHCP_POOL_END"])

    if lan_ip not in lan:
        raise ValueError("LAN_IP deve pertencer à LAN_CIDR")
    if docker_gw not in lan:
        raise ValueError("LAN_DOCKER_GATEWAY deve pertencer à LAN_CIDR")
    if docker_gw == lan_ip:
        raise ValueError("LAN_DOCKER_GATEWAY não pode ser igual ao LAN_IP")
    if not docker_range.subnet_of(lan):
        raise ValueError("LAN_DOCKER_IP_RANGE deve estar contida em LAN_CIDR")
    if lan_ip in docker_range:
        raise ValueError("LAN_DOCKER_IP_RANGE não pode conter o LAN_IP")

    if pool_start not in lan or pool_end not in lan:
        raise ValueError("DHCP_POOL_START e DHCP_POOL_END devem pertencer à LAN_CIDR")
    if int(pool_start) > int(pool_end):
        raise ValueError("DHCP_POOL_START deve ser menor ou igual a DHCP_POOL_END")
    if int(pool_start) <= int(lan_ip) <= int(pool_end):
        raise ValueError("o pool DHCP não pode conter o LAN_IP")
    if int(pool_start) <= int(docker_gw) <= int(pool_end):
        raise ValueError("o pool DHCP não deve conter o LAN_DOCKER_GATEWAY")

    pool_net_span = (int(pool_start), int(pool_end))
    docker_span = (int(docker_range.network_address), int(docker_range.broadcast_address))
    overlaps = pool_net_span[0] <= docker_span[1] and docker_span[0] <= pool_net_span[1]
    if overlaps:
        raise ValueError("o pool DHCP não pode sobrepor a LAN_DOCKER_IP_RANGE")

    parse_dns(cfg["DHCP_DNS"])
    parse_domain(cfg["DHCP_DOMAIN"])

    for key in ["FW_API_PORT", "KEA_CA_PORT", "FW_API_HOST_PORT", "KEA_CA_HOST_PORT"]:
        parse_port(cfg[key])

    if cfg["FW_API_PORT"] == cfg["KEA_CA_PORT"]:
        raise ValueError("FW_API_PORT e KEA_CA_PORT não podem ser iguais")
    if cfg["FW_API_HOST_PORT"] == cfg["KEA_CA_HOST_PORT"]:
        raise ValueError("FW_API_HOST_PORT e KEA_CA_HOST_PORT não podem ser iguais")


def ask_value(
    cfg: dict[str, str],
    key: str,
    validator: Callable[[str], object] | None = None,
    normalizer: Callable[[str], str] | None = None,
) -> None:
    current = cfg[key]
    while True:
        raw = input(f"{LABELS[key]} [{current}]: ").strip()
        value = raw if raw else current
        try:
            if validator:
                validator(value)
            cfg[key] = normalizer(value) if normalizer else value
            return
        except ValueError as exc:
            print(f"Valor inválido: {exc}")


def normalize_net(value: str) -> str:
    return str(parse_net(value))


def normalize_ip(value: str) -> str:
    return str(parse_ipv4(value))


def normalize_dns(value: str) -> str:
    return ", ".join(str(ip) for ip in parse_dns(value))


def show_config(cfg: dict[str, str]) -> None:
    print("\nConfiguração atual considerada pelo script:\n")
    for key in DEFAULTS:
        print(f"  {key:<22} {cfg[key]}")
    print("")


def main() -> int:
    cfg = read_env(ENV_FILE)
    show_config(cfg)

    try:
        validate_all(cfg)
    except ValueError as exc:
        print(f"A configuração atual possui inconsistência: {exc}")
        print("O assistente de configuração será iniciado para correção.\n")
    else:
        if not yes_no("Deseja modificar a configuração?", default=False):
            print("Nenhuma alteração realizada.")
            return 0

    while True:
        print("\nInforme os novos valores. Pressione Enter para manter o valor atual.\n")

        ask_value(cfg, "LAN_CIDR", parse_net, normalize_net)
        ask_value(cfg, "LAN_IP", parse_ipv4, normalize_ip)
        ask_value(cfg, "LAN_DOCKER_GATEWAY", parse_ipv4, normalize_ip)
        ask_value(cfg, "LAN_DOCKER_IP_RANGE", parse_net, normalize_net)
        ask_value(cfg, "DHCP_POOL_START", parse_ipv4, normalize_ip)
        ask_value(cfg, "DHCP_POOL_END", parse_ipv4, normalize_ip)
        ask_value(cfg, "DHCP_DNS", parse_dns, normalize_dns)
        ask_value(cfg, "DHCP_DOMAIN", parse_domain)
        ask_value(cfg, "FW_API_HOST_PORT", parse_port)
        ask_value(cfg, "KEA_CA_HOST_PORT", parse_port)

        # Normalmente não é necessário alterar as portas internas; ainda assim deixamos disponível.
        if yes_no("Deseja alterar também as portas internas dos serviços no container?", default=False):
            ask_value(cfg, "FW_API_PORT", parse_port)
            ask_value(cfg, "KEA_CA_PORT", parse_port)

        try:
            validate_all(cfg)
        except ValueError as exc:
            print(f"\nConfiguração inconsistente: {exc}")
            print("Vamos repetir os prompts para correção.")
            continue

        show_config(cfg)
        if yes_no("Confirmar e gravar o arquivo .env?", default=True):
            write_env(ENV_FILE, cfg)
            print(f"Arquivo {ENV_FILE} gravado com sucesso.")
            print("\nPróximos comandos sugeridos:")
            print("  docker compose down")
            print("  docker compose up -d --build")
            return 0

        if not yes_no("Deseja revisar os valores novamente?", default=True):
            print("Nenhuma alteração gravada.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
