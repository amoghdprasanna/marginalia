"""Cutting a release: version bump, changelog sections and links, tag checks."""

from datetime import date

import pytest
from release import bump_init, check, current_version, parse, release_changelog, section

INIT = '"""Marginalia."""\n__version__ = "0.1.0"\n'
LOG = """# Changelog

## [Unreleased]

### Added
- The journal browser.

## [0.1.0] - 2026-10-04

### Added
- The overlay.

[Unreleased]: https://github.com/amoghdprasanna/marginalia/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amoghdprasanna/marginalia/releases/tag/v0.1.0
"""


def test_versions():
    assert parse("1.2.3") == (1, 2, 3)
    with pytest.raises(ValueError):
        parse("1.2")
    assert current_version(INIT) == "0.1.0"
    assert current_version(bump_init(INIT, "0.2.0")) == "0.2.0"


def test_sections():
    assert section(LOG, "0.1.0") == "### Added\n- The overlay."
    assert section(LOG, "Unreleased") == "### Added\n- The journal browser."
    assert section(LOG, "9.9.9") is None


def test_release_moves_unreleased_under_the_version():
    out = release_changelog(LOG, "0.1.0", "0.2.0", date(2026, 10, 9))
    assert section(out, "0.2.0") == "### Added\n- The journal browser."
    assert section(out, "Unreleased") == ""
    assert "## [0.2.0] - 2026-10-09" in out
    assert "[Unreleased]: https://github.com/amoghdprasanna/marginalia/compare/v0.2.0...HEAD" in out
    assert "[0.2.0]: https://github.com/amoghdprasanna/marginalia/compare/v0.1.0...v0.2.0" in out
    assert section(out, "0.1.0") == "### Added\n- The overlay.", "older sections untouched"


def test_nothing_unreleased_is_refused():
    empty = release_changelog(LOG, "0.1.0", "0.2.0", date(2026, 10, 9))
    with pytest.raises(ValueError):
        release_changelog(empty, "0.2.0", "0.3.0", date(2026, 10, 10))


def test_tag_check():
    assert check("v0.1.0", INIT, LOG) == []
    assert check("v0.2.0", INIT, LOG) == [
        "tag v0.2.0 but __version__ is 0.1.0",
        "CHANGELOG.md has no section for 0.2.0",
    ]


def test_the_real_changelog_and_version_agree():
    from release import CHANGELOG
    from release import INIT as INIT_PATH

    text = CHANGELOG.read_text()
    version = current_version(INIT_PATH.read_text())
    assert section(text, version), f"CHANGELOG.md needs a section for {version}"
    assert section(text, "Unreleased") is not None
