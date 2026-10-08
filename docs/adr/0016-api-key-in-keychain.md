# 0016. The API key lives in the OS credential store

**Status:** Accepted, 2026-10-08

## Context
The API key sat in a plain-text `.env` file, readable by any process running as you, easy to
commit by accident, and copied along with the project folder. A settings window that asks for
the key must put it somewhere better than another plain file.

## Decision
- `secrets.Keychain` stores one secret (service `Marginalia`, account `anthropic-api-key`)
  through **`keyring`**: macOS Keychain, Windows Credential Locker, Secret Service on Linux.
  `keyring` becomes a core dependency.
- Resolution order: `ANTHROPIC_API_KEY` from the environment (or `.env`) first, then the
  keychain. The environment still wins so CI, the eval and existing setups behave as before.
- The key is read once at startup (and again when Settings saves), on the main thread. On
  macOS the first read may show the system "allow access" prompt; that is the point.
- `Keychain` never raises. No backend (headless Linux), a locked keychain or a missing package
  is logged and treated as "no key", and the Settings window shows the problem.
- The window shows only a masked key (`sk-ant-…abcd`). Nothing logs the key.

## Consequences
- The plain-text `.env` key keeps working but is no longer the recommended path; the README
  says to paste the key into Settings.
- Tests swap the backend for an in-memory fake (autouse fixture), so they never touch your
  real keychain.

## Alternatives considered
- **pyobjc `Security` calls / `security` CLI directly.** macOS-only; `keyring` already wraps
  all three platforms with one API and is pure Python.
- **Encrypt a file with a password.** You'd type the password every launch, or store it
  somewhere, which is the same problem again.
