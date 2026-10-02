# 0006. Local speech-to-text with faster-whisper

**Status:** Accepted, 2026-10-02

## Context
Voice questions need speech-to-text. The Claude API takes text and images, not audio. Questions
are short (2 to 20 s), often contain jargon ("stabilizer", "Pauli"), and are asked while a
lecture may be playing.

## Decision
Record with `sounddevice` at 16 kHz mono and transcribe on-device with faster-whisper
(`base.en`, int8, CPU). End-of-question is decided by `SilenceDetector`: it calibrates the room's
noise floor for 350 ms, treats anything 3x louder as speech, and stops after 1.4 s of quiet
following speech (or 45 s total). Enter or a click also ends it.

## Consequences
- No audio leaves the machine; works offline; no second API key.
- About 150 MB download on first use, warmed in the background at startup.
- `base.en` is English-only; `MARGINALIA_WHISPER_MODEL=small` handles other languages.
- The detector is pure and fully tested; its thresholds are guesses until measured with real
  rooms.
- OpenCV (from OCR) and PyAV (from Whisper) both bundle `libavdevice`; macOS prints a
  duplicate-class warning. Neither library's capture code is used, so it is harmless, but
  watch for it if crashes appear.

## Alternatives considered
- **macOS `SFSpeechRecognizer` via PyObjC:** no download, but macOS only, and an unbundled
  Python process cannot reliably get the speech-recognition permission.
- **A cloud STT API:** better accuracy on jargon, but sends audio off-device and adds a
  provider, a key and latency.
- **A VAD model (Silero) for end-of-speech:** more robust to noise, but another model; revisit
  if the energy detector misfires in practice.
