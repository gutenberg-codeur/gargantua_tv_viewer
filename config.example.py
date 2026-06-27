"""
Gargantua Configuration Template

Copy this file to config.py and adapt values to your environment:
    cp config.example.py config.py

Then update the following values:
  - SSH_TARGET: hostname/IP of your VDR server
  - VDR_LIVE_PORT: HTTP port of vdr-live plugin (default: 8008)
  - REMOTE_EPG_PATH: path to VDR EPG cache on server (default: /var/cache/vdr/epg.data)
  - LANGUAGE: UI language ("en", "fr", "de", "es")
"""

from datetime import timedelta

# ============================================================================
# Language Configuration
# ============================================================================

# Supported languages: "en" (English), "fr" (Français), "de" (Deutsch), "es" (Español)
LANGUAGE = "en"

# ============================================================================
# VDR Server Configuration
# ============================================================================

# SSH alias or hostname of your VDR server (e.g., "vdr-server", "192.168.1.100")
SSH_TARGET = "your-vdr-server"

# HTTP port where vdr-live plugin listens (default in VDR: 8008)
VDR_LIVE_PORT = 8008

# Base URL for video stream access (usually localhost via SSH tunnel)
BASE_URL = f"http://127.0.0.1:{VDR_LIVE_PORT}/TS"

# VDR commands via SSH (with timeout options for slow networks)
SSH_OPTIONS = [
    "-4",                             # Force IPv4 (disable IPv6 if your network blocks it)
    "-o", "ConnectTimeout=10",        # 10s timeout for initial connection
    "-o", "ServerAliveInterval=60",   # Send keepalive every 60s
    "-o", "ServerAliveCountMax=3",    # Disconnect after 3 failed keepalives
]
SVDRP_CMD = ["ssh"] + SSH_OPTIONS + [SSH_TARGET, "svdrpsend", "LSTC"]
SSH_TUNNEL_CMD = ["ssh"] + SSH_OPTIONS + ["-N", "-L",
                  f"{VDR_LIVE_PORT}:0.0.0.0:{VDR_LIVE_PORT}", SSH_TARGET]
SSH_SIGNAL_CMD = ["ssh"] + SSH_OPTIONS + [SSH_TARGET, "dvb-fe-tool -m -c 1 2>&1"]

# Remote EPG data file on VDR server
REMOTE_EPG_PATH = "/var/cache/vdr/epg.data"

# ============================================================================
# UI Configuration
# ============================================================================

DEBUG_POLL_MS = 2000
DEFAULT_CHANNEL = 1
TIMESHIFT_STEP_SECONDS = 15
BUTTON_SIZE = 25
RECORDING_START_MARGIN = timedelta(minutes=5)
RECORDING_END_MARGIN = timedelta(minutes=10)

# ============================================================================
# EPG & VDR Configuration
# ============================================================================

EPG_UNKNOWN_CHANNEL = 9999
VDR_TIMER_PRIORITY = 50
VDR_TIMER_LIFETIME = 99
CURSOR_HIDE_DELAY_MS = 3000
