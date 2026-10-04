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
| [0009](0009-model-defaults.md) | Model, effort and refusal fallback defaults | Accepted |
| [0010](0010-src-layout-and-packages.md) | `src/` layout, packages for brain and ui | Accepted |
| [0011](0011-structured-outputs-and-prompt-caching.md) | Structured outputs for the answer; cache the system prompt | Accepted |
| [0012](0012-stream-the-answer.md) | Stream the answer into the bubble | Accepted |
