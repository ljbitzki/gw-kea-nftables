import os
from pathlib import Path


def _load_dotenv():
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not candidate.exists():
            continue
        with candidate.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
        break


_load_dotenv()

STATE_FILE = Path(os.environ.get("FW_STATE_FILE", "/etc/gwapi/firewall_state.json"))
DHCP_RESERVATIONS_FILE = Path(os.environ.get("DHCP_RESERVATIONS_FILE", "/etc/gwapi/dhcp_reservations.json"))
KEA_LEASES_FILE = Path(os.environ.get("KEA_LEASES_FILE", "/var/lib/kea/kea-leases4.csv"))
LAN_IF = os.environ.get("LAN_IF", "eth1")
WAN_IF = os.environ.get("WAN_IF", "eth0")
LAN_CIDR = os.environ.get("LAN_CIDR", "10.88.0.0/24")
FW_API_PORT = int(os.environ.get("FW_API_PORT", "8080"))
KEA_CA_PORT = int(os.environ.get("KEA_CA_PORT", "8000"))
KEA_CA_URL = os.environ.get("KEA_CA_URL", f"http://127.0.0.1:{KEA_CA_PORT}/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "gwapi-dev-secret-change-me")
