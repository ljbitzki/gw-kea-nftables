import logging
import os
import sys
import time

from flask import g, request, session


def configure_logging(app):
    level_name = os.environ.get("GWAPI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [gwapi] %(levelname)s %(message)s"))

    for logger in (logging.getLogger("gwapi"), app.logger):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False


def mark_request_start():
    g.request_started_at = time.perf_counter()


def log_request_finished(response):
    started_at = getattr(g, "request_started_at", None)
    duration_ms = (time.perf_counter() - started_at) * 1000 if started_at else 0
    user = session.get("username") or "-"
    logging.getLogger("gwapi").info(
        "api_request method=%s path=%s status=%s duration_ms=%.1f endpoint=%s remote_addr=%s user=%s",
        request.method,
        request.path,
        response.status_code,
        duration_ms,
        request.endpoint or "-",
        request.remote_addr or "-",
        user,
    )
    return response
