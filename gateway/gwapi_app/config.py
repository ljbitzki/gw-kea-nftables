import os
from pathlib import Path


STATE_FILE = Path(os.environ.get("FW_STATE_FILE", "/etc/gwapi/firewall_state.json"))
LAN_IF = os.environ.get("LAN_IF", "eth1")
WAN_IF = os.environ.get("WAN_IF", "eth0")
LAN_CIDR = os.environ.get("LAN_CIDR", "10.88.0.0/24")
FW_API_PORT = int(os.environ.get("FW_API_PORT", "8080"))
KEA_CA_PORT = int(os.environ.get("KEA_CA_PORT", "8000"))
KEA_CA_URL = os.environ.get("KEA_CA_URL", f"http://127.0.0.1:{KEA_CA_PORT}/")
