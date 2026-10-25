# 0028. An installed app: a Windows installer, opening at login, and updating from the app

**Status:** Accepted, 2026-10-25. Supersedes the "not a self-installer (yet)" part of
[0021](0021-update-check.md); its daily check stays. Extends [0023](0023-pyinstaller-app.md).

## Context
People on macOS and Windows should never need a terminal: not to install Marginalia, not to
start it, not to update it. ADR 0023 gave us a `.app` and a Windows `.zip`, but:

- the Windows `.zip` is a folder you unpack somewhere, with no Start menu entry and no uninstaller;
- nothing starts the app when you log in, so every session began by launching it by hand;
- an update meant "Download…", a browser, and a drag into Applications (ADR 0021), because a
  self-updater was judged unsafe without a code signature to check the download against.

That last judgement deserves a second look. The manual route trusts exactly two things: HTTPS to
GitHub, and whoever can publish releases on this repository. An updater that downloads the same
file from the same place, over HTTPS, trusts nothing more, and since mid-2025 GitHub records a
**SHA-256 of every release asset at upload**, which can't be changed afterwards. Checking against
it catches a damaged or swapped download.

## Decision
**Windows: an Inno Setup installer**, `Marginalia-<v>-windows-setup.exe`, replacing the `.zip`.
- Per-user (`PrivilegesRequired=lowest`, into `%LOCALAPPDATA%\Programs\Marginalia`): no
  administrator prompt, and the app can update itself without one either.
- A Start menu entry, an optional desktop icon, an uninstaller, and "Launch Marginalia" at the end.
- A fixed `AppId`, so a newer installer finds the install it's updating.
- `packaging/build.py` compiles it when Inno Setup is found; the release workflow installs Inno
  Setup with Chocolatey (it is leaving GitHub's runner images) and checks the installer exists.

**Opening at login** (`autostart.LoginItem`, Settings → Startup and updates).
- macOS: a launch agent `~/Library/LaunchAgents/<bundle id>.plist` that runs
  `/usr/bin/open <the .app>` at login, with `AssociatedBundleIdentifiers` so Login Items shows it
  as Marginalia. Windows: a `Marginalia` value under `HKCU\…\CurrentVersion\Run`.
- **The system holds the state, not the settings file.** The checkbox reads it each time Settings
  opens, so switching it off in System Settings or Task Manager is respected. The uninstaller
  removes the Run value. If the app has moved, it repoints the item at itself on start.
- Off by default, and only for the installed app: a copy run from Python, or a Mac app still on
  the disk image, gets a disabled checkbox that says why.

**Updating from the app** (`selfupdate.Updater`, "Update now" in the update notice).
- Only the packaged app, and only for a release whose installer for this platform has a
  `sha256:` digest. Everywhere else the notice keeps "Download…", as before.
- The download must come from `https://github.com/<repo>/releases/download/`, may only be
  redirected to GitHub's download hosts over HTTPS, must not exceed the recorded size, and must
  match the recorded SHA-256. Otherwise it is deleted and nothing changes.
- **macOS:** mount the `.dmg` read-only, copy `Marginalia.app` to a hidden sibling of the running
  app (same disk, so the swap is a rename), check its bundle id and version match the release,
  and, **when this copy is signed by a developer team, that the new one is signed by the same
  team** (`codesign --verify --deep --strict`). A `/bin/sh` script then waits for the app's PID to
  exit, renames old → backup and new → old (restoring the backup if that fails), and opens it.
- **Windows:** a batch script waits for the app's PID to exit, then runs the new installer with
  `/SILENT` (a progress bar, no questions), which reuses the install folder and starts the app.
- The download runs on a worker with a progress window; Cancel, or closing that window, stops
  it. Leftovers from a cancelled or failed update are removed on the next start.
- Releases are built for Apple silicon (ADR 0023), so an Intel Mac is offered "Download…".

## Consequences
- **Unsigned Mac builds lose their permissions on every update.** macOS ties Screen Recording and
  microphone grants to the code signature; an ad-hoc signature is a hash of the exact build, so a
  new build is a new app to it. The progress window says so, and the setup check (ADR 0018)
  walks you through granting it again. A Developer ID (`docs/releasing.md`) ends this, because
  then the grant follows the team, and the updater also gets a signature to compare.
- Python's downloader doesn't set the quarantine flag (or Windows' mark of the web), so the new
  version opens without the Gatekeeper or SmartScreen prompt the first install showed. That is
  what makes "Update now" one click; it is also why the checksum and, on signed builds, the team
  check are not optional.
- The integrity check is only as strong as the repository's release permissions: someone who can
  publish a release here can publish a matching checksum. Signing (and, later, a signed update
  feed such as Sparkle's) raises that bar.
- Updating needs the releases to be readable without logging in, i.e. a **public** repository
  (or a public mirror of its releases). While it's private the check sees nothing, as ADR 0021
  already noted.
- Windows users of the old `.zip` aren't offered "Update now" (there's no uninstaller beside the
  executable); they install once with the installer and update from then on.

## Alternatives considered
- **Sparkle** (macOS) and **WinSparkle**. The standard updaters, with EdDSA-signed appcasts. Still
  the plan once builds are signed, but Sparkle is an Objective-C framework to embed and drive
  from Python, and with ad-hoc builds its signature checks would have nothing to compare.
- **Swap the bundle from Python in a re-launched copy of the new app.** No shell script, but the
  new copy would be replacing the folder it is running from, and a crash halfway leaves no app.
  A rename-and-restore in a tiny script is easier to reason about and to test.
- **On Windows, a portable `.zip` that swaps its own folder.** Workable, but no Start menu entry,
  no uninstaller, and we'd reimplement what an installer does when run over an existing install.
- **MSIX or an MSI (WiX).** MSIX needs a signing certificate to install at all; MSI per-user
  installs and silent upgrades are fiddlier than Inno Setup's for the same result.
- **`SMAppService` for the macOS login item** (macOS 13+). Apple's newer API, but it needs the
  ServiceManagement bindings, isn't there on macOS 12, which we support, and is designed around
  signed apps. A launch agent works everywhere and is a file we can read back.
- **A setting in the settings file for opening at login.** It would drift from what the system
  actually does as soon as you change it in System Settings or Task Manager.
