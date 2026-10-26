# Architecture Decision Records

One short file per decision that would be expensive to reverse or puzzling to a newcomer.
Each says what forced the decision, what we chose, what it costs us, and what we turned down.

Write a new one when you change a dependency, a data flow, a threading rule, or a boundary
between modules. Never edit an accepted ADR to say something different: add a new one that
supersedes it, so the history of *why* survives.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-native-overlay-with-qt.md) | Native overlay with PySide6 | Accepted |
| [0003](0003-resize-images-ourselves.md) | Resize screenshots to the API's exact size ourselves | Accepted |
| [0004](0004-points-as-json-snapped-to-ocr.md) | Points as JSON, snapped to OCR lines | Parsing superseded by 0011 |
| [0005](0005-optional-capabilities.md) | OCR and voice are optional and degrade gracefully | Accepted |
| [0006](0006-local-speech-to-text.md) | Local speech-to-text with faster-whisper | Accepted |
| [0007](0007-concurrency-model.md) | Worker pool, Qt signals and request ids | Accepted |
| [0008](0008-testable-core-thin-shell.md) | Testable core, thin Qt shell, fakes over mocks | Accepted |
| [0009](0009-model-defaults.md) | Model, effort and refusal fallback defaults | Model superseded by 0013 |
| [0010](0010-src-layout-and-packages.md) | `src/` layout, packages for brain and ui | Accepted |
| [0011](0011-structured-outputs-and-prompt-caching.md) | Structured outputs for the answer; cache the system prompt | Accepted |
| [0012](0012-stream-the-answer.md) | Stream the answer into the bubble | Accepted |
| [0013](0013-default-to-opus-5-5.md) | Default model: Claude Opus 5.5 | Accepted |
| [0014](0014-logging.md) | Log with `logging`: console lines, JSON lines in a file | Accepted |
| [0015](0015-settings-file-under-env.md) | A settings file, layered under environment variables | Accepted |
| [0016](0016-api-key-in-keychain.md) | The API key lives in the OS credential store | Accepted |
| [0017](0017-native-hotkeys-hold-to-talk.md) | Native hotkeys on macOS, and a hold-to-talk voice key | Accepted |
| [0018](0018-setup-check.md) | A setup check with fix-it buttons | Accepted |
| [0019](0019-journal-index-and-browser.md) | A journal index, and a browser that reopens threads | Accepted |
| [0020](0020-local-crash-reports-opt-in-sending.md) | Crash reports: always local, sent only through an issue you review | Accepted |
| [0021](0021-update-check.md) | Updates: a daily check that tells you, not a self-installer (yet) | Self-installer superseded by 0028 |
| [0022](0022-release-process.md) | Release process: SemVer, a changelog, and tag-triggered builds | Accepted |
| [0023](0023-pyinstaller-app.md) | The desktop app: PyInstaller, signed and notarised when credentials exist | Size and FFmpeg notes superseded by 0026 |
| [0024](0024-wayland-through-the-portal.md) | Wayland: screenshots and shortcuts through the desktop portal, windows through XWayland | Accepted |
| [0025](0025-markers-follow-their-content.md) | Markers follow what they point at | Accepted |
| [0026](0026-apple-vision-ocr-and-a-leaner-app.md) | OCR with Apple Vision on macOS, and a leaner app | Accepted |
| [0027](0027-more-than-one-model-provider.md) | More than one model provider: Claude, OpenAI and Gemini | Accepted |
| [0028](0028-installers-login-item-and-in-app-updates.md) | An installed app: a Windows installer, opening at login, and updating from the app | Accepted |
