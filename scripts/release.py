"""Cut a release: bump the version and turn the changelog's "Unreleased" into that version.

    python scripts/release.py 0.2.0          # edits src/marginalia/__init__.py and CHANGELOG.md
    python scripts/release.py --notes 0.2.0  # print that version's changelog section (CI uses it)
    python scripts/release.py --check v0.2.0 # exit 1 unless the tag, __version__ and changelog agree

It never commits, tags or pushes; it prints the commands for that. See docs/releasing.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "marginalia" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/amoghdprasanna/marginalia"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.M)


def parse(v: str) -> tuple[int, int, int]:
    m = SEMVER.match(v)
    if m is None:
        raise ValueError(f"'{v}' is not a version like 1.2.3")
    return tuple(int(x) for x in m.groups())


def current_version(init_text: str) -> str:
    m = _VERSION_LINE.search(init_text)
    if m is None:
        raise ValueError("no __version__ line")
    return m.group(1)


def bump_init(init_text: str, new: str) -> str:
    return _VERSION_LINE.sub(f'__version__ = "{new}"', init_text, count=1)


def section(changelog: str, version: str) -> str | None:
    """The body under '## [version]', without its heading."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def release_changelog(changelog: str, old: str, new: str, today: date) -> str:
    """Move Unreleased under a new version heading, start a fresh Unreleased, fix the links."""
    body = section(changelog, "Unreleased")
    if not body:
        raise ValueError("nothing under [Unreleased] to release")
    changelog = re.sub(
        r"^## \[Unreleased\]\n",
        f"## [Unreleased]\n\n## [{new}] - {today.isoformat()}\n",
        changelog,
        count=1,
        flags=re.M,
    )
    changelog = re.sub(
        r"^\[Unreleased\]: .*$",
        f"[Unreleased]: {REPO_URL}/compare/v{new}...HEAD\n[{new}]: {REPO_URL}/compare/v{old}...v{new}",
        changelog,
        count=1,
        flags=re.M,
    )
    return changelog


def check(tag: str, init_text: str, changelog: str) -> list[str]:
    problems = []
    version = tag.removeprefix("v")
    if current_version(init_text) != version:
        problems.append(f"tag {tag} but __version__ is {current_version(init_text)}")
    if not section(changelog, version):
        problems.append(f"CHANGELOG.md has no section for {version}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("version", help="X.Y.Z (or vX.Y.Z with --check)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--notes", action="store_true", help="print the changelog section for VERSION")
    group.add_argument("--check", action="store_true", help="verify a tag against __version__ and the changelog")
    args = ap.parse_args(argv)
    init_text, changelog = INIT.read_text(), CHANGELOG.read_text()

    if args.notes:
        body = section(changelog, args.version.removeprefix("v"))
        if body is None:
            print(f"No changelog section for {args.version}", file=sys.stderr)
            return 1
        print(body)
        return 0
    if args.check:
        problems = check(args.version, init_text, changelog)
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1 if problems else 0

    old, new = current_version(init_text), args.version
    try:
        if parse(new) <= parse(old):
            print(f"error: {new} is not newer than {old}", file=sys.stderr)
            return 1
        CHANGELOG.write_text(release_changelog(changelog, old, new, date.today()))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    INIT.write_text(bump_init(init_text, new))
    print(f"Version {old} -> {new}. Review the diff, then:")
    print(f'  git commit -am "chore: release {new}" && git tag v{new} && git push origin main v{new}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
