"""Is there a newer release? A once-a-day look at GitHub's latest release (ADR 0021).

Pure apart from `fetch_latest`, whose HTTP opener is injectable. Nothing is downloaded or
installed here: the app tells you, and "Download" opens the release in your browser.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import RELEASES_API, __version__

log = logging.getLogger(__name__)

CHECK_EVERY = timedelta(days=1)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(a|b|rc)(\d+))?$")
_PRE = {"a": 0, "b": 1, "rc": 2}


def parse_version(text: str) -> tuple | None:
    """'v1.2.3' / '1.2.3rc1' -> a sortable tuple; None if it isn't a version we understand.

    A pre-release sorts before its final release: 1.2.3rc1 < 1.2.3.
    """
    m = _VERSION.match(text.strip())
    if m is None:
        return None
    major, minor, patch, pre, n = m.groups()
    tail = (_PRE[pre], int(n)) if pre else (3, 0)
    return (int(major), int(minor), int(patch), *tail)


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


@dataclass
class Release:
    version: str
    url: str  # the release page
    notes: str = ""
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download URL

    def download_url(self, platform: str = sys.platform) -> str:
        """The installer for this platform if the release has one, else the release page."""
        wanted = {"darwin": ".dmg", "win32": ".zip"}.get(platform)
        for name, url in self.assets.items():
            if wanted and name.endswith(wanted):
                return url
        return self.url


def fetch_latest(url: str = RELEASES_API, opener=urllib.request.urlopen, timeout: float = 5.0) -> Release | None:
    """The newest published release, or None (offline, rate-limited, private repo, no releases)."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"Marginalia/{__version__}"}
    )
    try:
        with opener(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001  (URLError, HTTPError 404/403, timeouts, bad JSON)
        log.debug("Update check failed: %s", exc)
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if parse_version(tag) is None:
        return None
    assets = {a.get("name", ""): a.get("browser_download_url", "") for a in data.get("assets") or []}
    return Release(tag.lstrip("v"), str(data.get("html_url") or ""), str(data.get("body") or ""), assets)


def due(last_checked: str | None, now: datetime | None = None) -> bool:
    """True when the last check (ISO time from the settings file) was a day or more ago."""
    if not last_checked:
        return True
    try:
        then = datetime.fromisoformat(last_checked)
    except ValueError:
        return True
    return (now or datetime.now()) - then >= CHECK_EVERY
