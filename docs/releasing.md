# Releasing

Versions follow [SemVer](https://semver.org/): while we're at 0.x, a minor bump (0.2 → 0.3) for
features, a patch (0.2.0 → 0.2.1) for fixes only. Every user-visible change gets a line under
`## [Unreleased]` in `CHANGELOG.md` in the same PR that makes it.

## Cutting a release

```bash
git switch main && git pull
python scripts/release.py 0.2.0      # bumps __version__, moves Unreleased under 0.2.0
git diff                              # read the changelog section: it becomes the release notes
git commit -am "chore: release 0.2.0"
git tag v0.2.0
git push origin main v0.2.0
```

The tag starts `.github/workflows/release.yml`: it checks that the tag, `__version__` and the
changelog agree, runs the tests, builds the wheel, the macOS disk image and the Windows installer, and
publishes a GitHub release with that changelog section as its notes. Running the workflow by hand
from the Actions tab builds everything without publishing (a dry run).

Users find out from the app's daily update check (ADR 0021), and the installed app updates itself
with **Update now** (ADR 0028). That needs the releases to be public, and each release's installers
to keep the names `packaging/build.py` gives them (`-macos.dmg`, `-windows-setup.exe`): the app
looks for those, and checks them against the SHA-256 GitHub records when they are uploaded.

## Building the app yourself

```bash
pip install -e ".[package,ocr,voice,openai,gemini]"
python packaging/build.py             # macOS: dist/Marginalia.app and dist/Marginalia-<v>-macos.dmg
```

On Windows, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) first (`choco install innosetup`)
to get `dist/Marginalia-<v>-windows-setup.exe`; without it the build falls back to a `.zip`.

## Signing and notarising (macOS)

Without these the app is ad-hoc signed: it runs on the Mac that built it, and Gatekeeper blocks
it everywhere else. With them, `packaging/build.py` signs with the hardened runtime, notarises
the app and the disk image, and staples the tickets. One-time setup (needs an Apple Developer
account, $99/year):

1. Create a **Developer ID Application** certificate (Xcode > Settings > Accounts, or
   developer.apple.com), export it with its private key as a `.p12` with a password.
2. Create an **app-specific password** for your Apple ID at account.apple.com.
3. In the GitHub repo, Settings > Secrets and variables > Actions, add:

| Secret | Value |
|---|---|
| `MACOS_CERT_P12` | `base64 -i cert.p12 \| pbcopy`, then paste |
| `MACOS_CERT_PASSWORD` | the `.p12` password |
| `MACOS_SIGN_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID1234)` |
| `APPLE_ID` | your Apple ID email |
| `APPLE_TEAM_ID` | the 10-character team id |
| `APPLE_APP_PASSWORD` | the app-specific password |

Locally, export the same names as environment variables before `python packaging/build.py`.
