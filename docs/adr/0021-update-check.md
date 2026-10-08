# 0021. Updates: a daily check that tells you, not a self-installer (yet)

**Status:** Accepted, 2026-10-08

## Context
The roadmap asks for auto-update. A real self-updater for a macOS app (download, verify the
signature, replace the bundle, relaunch) is only safe for a **signed** app: without a signature
to check, "auto-update" means running whatever the download contains. Signing needs an Apple
Developer ID that this project doesn't have yet (ADR 0023).

## Decision
- `updates.fetch_latest` asks the GitHub API for the latest **published, non-pre-release**
  release (stdlib `urllib`, 5 s timeout, no dependency). Any failure (offline, rate limit, the
  repository being private, no releases) is logged at DEBUG and treated as "no update".
- At most once a day (Settings: "Check for new versions once a day", on by default), after
  startup, on a worker thread. The time of the last check lives in `state.json`, next to the
  settings file but separate from it: bookkeeping must not count as "settings saved", which
  would hide the first-run setup check (ADR 0018).
- A newer version (SemVer, pre-releases sort before their release) is announced **once** in a
  small window with the release notes, and stays in the orb menu as "Update to X…". Download
  opens the platform's installer asset (`.dmg`, Windows `.zip`) or the release page.
- "Check for updates" in the orb menu checks immediately and says when you're up to date.

## Consequences
- Updating is two clicks and a drag into Applications, not zero. Honest about what is verified.
- The request reveals your IP and app version to GitHub once a day; the setting turns it off.
- While the repository is private, the unauthenticated check sees nothing; it starts working when
  releases are public, with no change here.

## Next step
Once builds are signed and notarised: adopt **Sparkle** (the standard macOS updater, with EdDSA-
signed appcasts) for the `.app`, and keep this check for the pip-installed version, which
updates with `pip install -U`.

## Alternatives considered
- **Download and swap the bundle ourselves now.** Unsigned code replacing unsigned code, with
  no way to tell a tampered download from a real one.
- **PyUpdater / tufup.** TUF-style signed updates are the right idea, but a second signing
  system and a hosted repository to run, before the platform signature even exists.
