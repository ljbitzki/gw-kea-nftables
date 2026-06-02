#!/usr/bin/env python3
import argparse
import logging
import sys

from gwapi_app import create_app
from gwapi_app.config import FW_API_PORT
from gwapi_app.dhcp_service import apply_reservations
from gwapi_app.firewall import apply_rules

app = create_app()
logger = logging.getLogger("gwapi")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-once", action="store_true")
    args = parser.parse_args()

    if args.apply_once:
        try:
            logger.info("startup_apply_once action=apply_firewall")
            apply_rules()
        except Exception as exc:  # noqa: BLE001
            logger.exception("startup_apply_once_failed error=%s", exc)
            return 1
        return 0

    logger.info("startup action=apply_firewall")
    apply_rules()
    try:
        logger.info("startup action=apply_dhcp_reservations retries=5 delay=1")
        apply_reservations(retries=5, delay=1)
    except Exception as exc:  # noqa: BLE001 - API de laboratório
        logger.warning("startup_dhcp_reservations_failed error=%s", exc)
    logger.info("startup action=run_api host=0.0.0.0 port=%s", FW_API_PORT)
    app.run(host="0.0.0.0", port=FW_API_PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
