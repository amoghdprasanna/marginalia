"""API keys, kept in the operating system's credential store instead of a plain-text file.

macOS Keychain, Windows Credential Locker, or the Secret Service on Linux, through `keyring`
(ADR 0016). One account per provider (ADR 0027). Where no store works (a headless Linux box),
it says so and the app falls back to the provider's variable (ANTHROPIC_API_KEY, ...) from the
environment or .env.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

SERVICE = "Marginalia"
ACCOUNT = "anthropic-api-key"  # the default; providers.Provider.account names the others


def _default_backend():
    import keyring

    return keyring


class Keychain:
    """get/set/delete a provider's key (`account`). Never raises: a broken store logs and acts empty."""

    def __init__(self, backend=None) -> None:
        self._backend = backend
        self.problem: str | None = None

    def _store(self):
        if self._backend is None:
            self._backend = _default_backend()
        return self._backend

    def get(self, account: str = ACCOUNT) -> str | None:
        try:
            return self._store().get_password(SERVICE, account) or None
        except Exception as exc:  # noqa: BLE001  (ImportError, NoKeyringError, a locked keychain...)
            self.problem = str(exc) or type(exc).__name__
            log.debug("Keychain unavailable: %s", self.problem)
            return None

    def set(self, key: str, account: str = ACCOUNT) -> bool:
        try:
            self._store().set_password(SERVICE, account, key.strip())
            self.problem = None
            return True
        except Exception as exc:  # noqa: BLE001
            self.problem = str(exc) or type(exc).__name__
            log.warning("Could not save the API key to the keychain: %s", self.problem)
            return False

    def delete(self, account: str = ACCOUNT) -> bool:
        try:
            self._store().delete_password(SERVICE, account)
            return True
        except Exception as exc:  # noqa: BLE001  (PasswordDeleteError when there was none)
            log.debug("Nothing deleted from the keychain: %s", exc)
            return False


def mask(key: str | None) -> str:
    """Enough of a key to recognise it, never enough to use it."""
    if not key:
        return ""
    return f"{key[:7]}…{key[-4:]}" if len(key) > 14 else "…"
