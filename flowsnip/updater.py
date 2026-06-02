"""
Update checker for FlowSnip and yt-dlp.

Pure logic module — no GUI imports. All network calls are fire-and-forget
with a hard timeout; failures are silently swallowed so they never block
or crash the app.
"""

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional


_FLOWSNIP_API = "https://api.github.com/repos/rajeshsub/FlowSnip/releases/latest"
_YTDLP_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
_TIMEOUT = 5  # seconds

FREQUENCY_EVERY_LAUNCH = "every_launch"
FREQUENCY_DAILY = "daily"
FREQUENCY_WEEKLY = "weekly"
FREQUENCY_NEVER = "never"

_FREQUENCY_DELTAS = {
    FREQUENCY_DAILY: timedelta(days=1),
    FREQUENCY_WEEKLY: timedelta(weeks=1),
}


def _fetch_latest_tag(api_url: str) -> Optional[str]:
    """Return the tag_name of the latest GitHub release, or None on any error."""
    try:
        req = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "FlowSnip"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        return data.get("tag_name")
    except Exception:
        return None


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest tag is strictly newer than current version string."""
    def _parts(v: str):
        return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())

    try:
        return _parts(latest) > _parts(current)
    except Exception:
        return False


def check_flowsnip_update(current_version: str) -> Optional[str]:
    """Return the latest FlowSnip tag if newer than current_version, else None."""
    latest = _fetch_latest_tag(_FLOWSNIP_API)
    if latest and _is_newer(latest, current_version):
        return latest
    return None


def check_ytdlp_update(current_version: str) -> Optional[str]:
    """Return the latest yt-dlp tag if newer than current_version, else None."""
    latest = _fetch_latest_tag(_YTDLP_API)
    if latest and _is_newer(latest, current_version):
        return latest
    return None


def should_check(last_checked: Optional[datetime], frequency: str) -> bool:
    """Return True if a check should run given the frequency setting."""
    if frequency == FREQUENCY_NEVER:
        return False
    if frequency == FREQUENCY_EVERY_LAUNCH:
        return True
    if last_checked is None:
        return True
    delta = _FREQUENCY_DELTAS.get(frequency)
    if delta is None:
        return True
    now = datetime.now(tz=timezone.utc)
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    return now - last_checked >= delta


def update_ytdlp() -> bool:
    """Upgrade yt-dlp in-place using pip. Returns True on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False
