# 0025. Markers follow what they point at

**Status:** Accepted, 2026-10-09

## Context
Markers were placed once, in screen coordinates from the screenshot the answer was about. Scroll
the page, switch windows, or (since commit 35bb6e0 put them on every desktop) switch
desktops, and they kept pointing at whatever now sat there. Wrong pointing is worse than none.

## Decision
- When markers land, `tracking.Tracker` keeps a small grayscale picture (~190 x 66 points) of
  what is under each one, cut from the screenshot the model saw (which has no markers on it).
- Once a second while markers are up, the controller grabs the screen, has Qt shrink it to
  480 px wide grayscale, and hands it to the tracker on the worker pool:
  - **still there?** normalised correlation with the same spot, ignoring the pixels our own ring
    and label cover (the screenshot includes our overlay);
  - **moved?** search the whole frame (FFT cross-correlation with integral-image normalisation);
    a good match moves the marker there;
  - **gone?** neither matches: the marker hides, and comes back if the content does.
- Patches too flat to be distinctive (blank margin) are left alone rather than guessed at.
- Tracking starts after the markers land (their flight would look like change), stops with the
  thread or a new question, and "Show again" flies to where things are now.
- Off on Wayland: there each grab is a portal round trip, not something to do every second.

## Consequences
- Scrolling a paper keeps the marker on its equation; switching away hides it.
- Up to one second of lag, and ~1 grab per second (tens of ms on the main thread at Retina size,
  plus ~0.3 ms matching when nothing moved, ~50 ms on the worker after a scroll).
- Content that changes in place (an animation under the marker) reads as "gone".
- Frames live only in memory, only while markers are up.

## Alternatives considered
- **Exclude our windows from capture** (`NSWindow.sharingType = none`), then compare plainly.
  Cleaner, but how macOS 15+ capture APIs honour it is inconsistent, and it is macOS-only.
- **Hide markers on any change** (Space switch notification, frontmost-app change). Simple, but
  scrolling, the commonest change, sends no such notification, and hiding is worse than following.
- **Re-ask the model.** Seconds and money per scroll.
- **OpenCV `matchTemplate`.** Faster, but OpenCV only comes with the optional OCR extra; numpy
  FFT is plenty at 480 px.
