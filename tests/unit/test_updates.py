"""The update check: version order, reading GitHub's answer, once a day."""

import io
import json
from datetime import datetime, timedelta
from urllib.error import URLError

import pytest

from marginalia.updates import Release, due, fetch_latest, is_newer, parse_version


@pytest.mark.parametrize(
    ("a", "b"),
    [("0.2.0", "0.1.0"), ("v1.0.0", "0.9.9"), ("0.10.0", "0.9.0"), ("1.0.0", "1.0.0rc1"), ("1.0.0rc2", "1.0.0b5")],
)
def test_newer(a, b):
    assert is_newer(a, b) and not is_newer(b, a)


def test_same_or_garbage_is_not_newer():
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("nightly", "0.1.0") and not is_newer("0.2.0", "dev")
    assert parse_version("1.2") is None


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_returning(data):
    def opener(request, timeout):
        assert request.get_header("User-agent").startswith("Marginalia/")
        return FakeResponse(json.dumps(data).encode())

    return opener


RELEASE = {
    "tag_name": "v0.3.0",
    "html_url": "https://github.com/o/r/releases/tag/v0.3.0",
    "body": "Faster answers.",
    "assets": [
        {"name": "Marginalia-0.3.0-macos.dmg", "browser_download_url": "https://x/m.dmg"},
        {"name": "Marginalia-0.3.0-windows.zip", "browser_download_url": "https://x/w.zip"},
    ],
}


def test_fetch_reads_the_release():
    r = fetch_latest(opener=opener_returning(RELEASE))
    assert (r.version, r.notes) == ("0.3.0", "Faster answers.")
    assert r.download_url("darwin") == "https://x/m.dmg"
    assert r.download_url("win32") == "https://x/w.zip"
    assert r.download_url("linux") == RELEASE["html_url"]


@pytest.mark.parametrize("data", [{**RELEASE, "prerelease": True}, {**RELEASE, "draft": True}, {"tag_name": "x"}, []])
def test_fetch_ignores_what_it_should_not_offer(data):
    assert fetch_latest(opener=opener_returning(data)) is None


def test_fetch_failures_are_quiet(caplog):
    def offline(request, timeout):
        raise URLError("no network")

    assert fetch_latest(opener=offline) is None
    assert "Update check failed" in caplog.text


def test_once_a_day():
    now = datetime(2026, 10, 8, 12, 0)
    assert due(None, now) and due("garbage", now)
    assert not due((now - timedelta(hours=3)).isoformat(), now)
    assert due((now - timedelta(days=1, minutes=1)).isoformat(), now)


def test_release_without_installer_points_at_the_page():
    assert Release("1.0.0", "https://page").download_url("darwin") == "https://page"
