# 0034. MIT license, and signing the Windows installer through SignPath Foundation

**Status:** Accepted, 2026-11-11. The signing half waits on SignPath Foundation accepting the
project. Extends [0023](0023-pyinstaller-app.md) and [0028](0028-installers-login-item-and-in-app-updates.md).

## Context
The Windows installer is unsigned. Windows SmartScreen flags it on download and again on launch
("Windows protected your PC", publisher unknown), and a tester reported exactly that. An
Authenticode signature needs a certificate from a CA Microsoft trusts, tied to a verified
identity; it can't be self-made.

The repository is public but had no license, which legally means all rights reserved: nobody
else could use, change or redistribute the code. That also kept it out of free signing programs,
which take only open-source projects.

## Decision
**The project is MIT-licensed** (`LICENSE`, `license = "MIT"` in `pyproject.toml`; the notebook
extension's `package.json` already said MIT). Permissive and short; it sits fine alongside the
bundled dependencies (PySide6 under the LGPL, the provider SDKs, Pillow, NumPy and the rest under
MIT, BSD or Apache licenses).

**Windows releases are to be signed through SignPath Foundation**, which signs open-source
projects for free with its own certificate. The README carries the policy it asks for (who
commits, reviews and approves signing; only artifacts built by this repository's release
workflow from a tag are submitted) and a privacy section listing everything the app sends over
the network. Once accepted, the Windows job in `release.yml` uploads the PyInstaller output and
the installer to SignPath, which checks they came from that workflow run, signs them, and hands
them back before the release is published.

## Consequences
- Windows shows "SignPath Foundation" as the publisher, not the author's name.
- SmartScreen reputation builds on SignPath's certificate, which many projects already use, so
  warnings should fade sooner than with a new certificate of our own. It isn't guaranteed: a
  newly signed file can still warn until enough people have downloaded it.
- Each signing request is approved by hand in SignPath, so a release waits for that click.
- The privacy section has to stay true: a feature that sends something new over the network
  updates it in the same change.
- Anyone may now fork and redistribute Marginalia, including in closed products, as long as the
  copyright notice stays.

## Alternatives considered
- **Azure Artifact Signing** (about $10 a month): the author's name as publisher and no review
  queue, but a monthly cost and an identity check. The fallback if SignPath declines.
- **A certificate from a CA** (Sectigo, DigiCert…; about $200–500 a year): the private key must
  live on a hardware token or cloud HSM, which is awkward in CI, and since 2024 even EV
  certificates no longer skip SmartScreen's reputation check.
- **Leave it unsigned:** every Windows user clicks "More info → Run anyway", and some won't.
- **GPL-3.0 instead of MIT:** would keep forks open, but asks more of anyone reusing the code than
  a study tool needs to.
