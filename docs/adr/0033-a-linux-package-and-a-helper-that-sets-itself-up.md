# 0033. A Linux package, and a helper that sets itself up

**Status:** Accepted, 2026-11-06. Extends [0028](0028-installers-login-item-and-in-app-updates.md)
and [0030](0030-fix-notebook-errors-through-a-desktop-helper.md).

## Context
The macOS disk image and the Windows installer (ADR 0028) let people install Marginalia without a
terminal. Two things still needed one: Linux, which only ran from source, and the notebook
extension, whose helper had to be registered with `marginalia-browser-host install` from the
right Python environment. A student opening the panel was asked to run a command in a terminal
they may never have used.

## Decision
**Linux gets a `.deb`.** `packaging/build.py` on Linux wraps the PyInstaller folder in
`marginalia_<version>_amd64.deb` with `dpkg-deb`: the app in `/opt/marginalia`, `/usr/bin/marginalia`,
a menu entry and the icon, and `Depends` on what the bundled Qt and PortAudio load from the
system (xcb, GL, GLib, fontconfig, D-Bus, PortAudio). A double-click opens it in the Software app;
removing it removes everything it put there. It is built on Ubuntu 22.04, the oldest release we
support, because glibc runs forward but not back; CI installs it, runs it and removes it.

**The installed app registers the extension's helper itself.** At every start, a frozen app calls
`browser.install.register_app()`: it writes the helper manifest into each Chrome, Chromium, Brave
and Edge profile folder (on Windows, the registry values) wherever the manifest is missing or names
another program, and does nothing when it is already right. A moved app finds its way back; an
unwritable folder is skipped without stopping the app. On top of that:
- the Windows installer runs `Marginalia.exe --register-browser-helper` once, and its uninstaller
  removes the registry values and the manifest file;
- the `.deb` ships the manifest system-wide in `/etc/opt/chrome`, `/etc/chromium` and
  `/etc/opt/edge`, so the extension works before the app has ever started;
- the disk image can run nothing, so on macOS the first start does it.

`marginalia-browser-host install` stays for source checkouts, and a copy run from Python never
overwrites a registration: the developer chose which helper the browser runs.

**The extension ships as a zip with each release** (`Marginalia-<version>-chrome-extension.zip`),
built by CI from `extension/`. Installing it is still Chrome's *Load unpacked*, but with a folder
you download rather than one you build.

**Linux updates by download.** "Download…" in the update notice opens the new `.deb`; the app
doesn't install over itself, because `/opt/marginalia` belongs to the package manager and
replacing it needs an administrator password the app shouldn't ask for.

## Consequences
- The installed app takes over the helper registration from a source checkout on the same
  computer at its next start. Running `marginalia-browser-host install` from the checkout again
  gives it back until the app starts.
- The `.deb` is large (about 215 MB, 800 MB installed): it carries the same RapidOCR, OpenCV and
  speech-to-text libraries as the Windows build. A lighter package without them is possible later.
- amd64 only, and Debian-family only. Fedora and Arch users run from source until there is
  demand for an `.rpm`, an AppImage or a Flatpak.
- Uninstalling the `.deb` can't reach per-user manifests in each home folder. They are left
  naming a program that no longer exists, which Chrome reports as "helper not found", the same
  state as never having installed it.
- The extension still needs *Load unpacked* and Developer mode. Only the Chrome Web Store removes
  that step; Chrome on macOS and Windows refuses extensions installed from local files.

## Alternatives considered
- **AppImage.** One file that runs anywhere, but no menu entry or helper registration without
  a first run, no dependency handling, and "make it executable" is itself a step people trip on.
- **Flatpak or Snap.** Sandboxed: screenshots, global shortcuts and talking to Chrome's native
  messaging would each need portals or permissions to be granted, for an app whose whole job is
  reading the screen.
- **Register the helper only from the installers.** The disk image can't run anything, and an app
  that moves would leave a stale path behind; registering at start covers both.
- **A system-wide manifest on macOS and Windows.** It needs administrator rights, which neither
  installer asks for (ADR 0028).
