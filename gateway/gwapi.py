#!/usr/bin/env python3
import argparse
import sys

from gwapi_app import create_app
from gwapi_app.config import FW_API_PORT
from gwapi_app.dhcp_service import apply_reservations
from gwapi_app.firewall import apply_rules

app = create_app()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-once", action="store_true")
    args = parser.parse_args()

    if args.apply_once:
        try:
            apply_rules()
        except Exception as exc:  # noqa: BLE001
            print(f"erro aplicando nftables: {exc}", file=sys.stderr)
            return 1
        return 0

    apply_rules()
    try:
        apply_reservations(retries=5, delay=1)
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        print(f"aviso: não consegui aplicar reservations DHCP: {exc}", file=sys.stderr)
    app.run(host="0.0.0.0", port=FW_API_PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
