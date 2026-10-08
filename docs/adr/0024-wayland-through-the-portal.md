# 0024. Wayland: screenshots and shortcuts through the desktop portal, windows through XWayland

**Status:** Accepted, 2026-10-08

## Context
On a Wayland session nothing worked: Qt's screen grab returns black, global keyboard hooks are
impossible by design, and native Wayland ignores window positions, so the orb, the bubble and
the markers can't be placed. Most Linux desktops now default to Wayland.

## Decision
- **Screenshots:** the `org.freedesktop.portal.Screenshot` portal, non-interactive. It returns a
  file with the whole desktop; we crop the screen asked about (logical geometry scaled to the
  image), then delete the file so screenshots don't pile up in Pictures. The first time, the
  desktop may ask you to allow it.
- **Shortcuts:** the `org.freedesktop.portal.GlobalShortcuts` portal (KDE Plasma, GNOME 48+,
  Hyprland). Its `Activated`/`Deactivated` signals give press *and* release, so hold-to-talk
  works there too. We suggest our keys as `preferred_trigger` (XDG spelling, `CTRL+ALT+space`);
  the desktop may show a dialog to confirm or change them, and what you choose is what fires.
  `PortalHotkeys` is a hotkeys backend like Carbon and pynput (ADR 0017).
- **Windows:** when the session is Wayland and XWayland is available (`DISPLAY` set), `main` runs
  Qt with `QT_QPA_PLATFORM=xcb`, so window placement and stay-on-top work as on X11. Setting
  `QT_QPA_PLATFORM` yourself overrides this.
- **D-Bus** through **jeepney**, a pure-Python library that `keyring` already pulls in on Linux.
  `Portal` is a two-method interface (a call answered by `Request.Response`; listening for
  signals), so the screenshot and shortcut logic is tested anywhere with a fake, and the jeepney
  layer is tested against a fake connection. Signals are read on a second connection in a daemon
  thread; callbacks only emit Qt signals.

## Consequences
- The pointer position: under XWayland, Qt only sees the cursor while it is over an XWayland
  window, so "where the mouse rested" is often stale on Wayland and the hotkey may ask about an
  older spot. Screenshots are still of the right screen; the cursor ring may be off. There is no
  portal for the global pointer position.
- The capture call blocks the UI thread while the portal answers (instant after the first
  permission). Acceptable for one question at a time.
- Verified by tests with fakes, not on a real Wayland desktop from this repository's CI (which has
  no desktop session). The first real run on GNOME and KDE should be checked by hand.

## Alternatives considered
- **PipeWire screencast (ScreenCast portal).** Continuous video, a permission dialog per
  session, and a GStreamer or PipeWire dependency, to take one still image.
- **Compositor-specific tools** (`grim` on wlroots, `spectacle`, `gnome-screenshot`). Each works on
  one family of desktops; the portal is the cross-desktop API they converge on.
- **`dbus-python` / `QtDBus`.** dbus-python needs a C build and system headers; QtDBus works but
  connecting PySide slots to D-Bus signals with `a{sv}` arguments is fragile, and it would put Qt
  into code that has no other reason to need it.
- **Native Wayland Qt with `wlr-layer-shell`** for placement. Only on wlroots compositors, and not
  exposed by Qt.
