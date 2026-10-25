"""SDK errors -> BrainErrors worded for the bubble.

The anthropic and openai SDKs are generated from the same template, so their exception classes
have the same names and meanings; `friendly` takes the SDK module and maps either.
"""
from __future__ import annotations

from .types import BrainError


def missing_key(name: str) -> BrainError:
    return BrainError(
        f"Marginalia needs a {name} API key to answer. Add one in Settings; it is kept in your keychain.", "settings"
    )


def missing_sdk(name: str, hint: str) -> BrainError:
    return BrainError(f"Asking {name} needs its library, which isn't installed. Run: {hint}", "settings")


def friendly(sdk, exc: Exception, name: str, model: str) -> BrainError:
    """`exc` from `sdk` (the anthropic or openai module) as a BrainError naming `name` ("Claude")."""
    msg = str(exc)
    if isinstance(exc, sdk.BadRequestError):
        if "image" in msg and ("exceed" in msg or "too large" in msg):
            return BrainError(
                "This model can't take screenshots that large. Turn off High-resolution images in Settings.",
                "settings",
            )
        return BrainError(f"{name} couldn't process this request ({msg[:200]}).")
    if isinstance(exc, sdk.AuthenticationError):
        return BrainError("Your API key was rejected. Check it in Settings.", "settings")
    if isinstance(exc, sdk.NotFoundError):
        return BrainError(f"The model '{model}' isn't available to your key. Pick another in Settings.", "settings")
    if isinstance(exc, sdk.RateLimitError):
        if "insufficient_quota" in msg:  # OpenAI says "out of credit" with a 429
            return BrainError(f"Your {name} account is out of credit. Check its billing page, then try again.")
        return BrainError("Too many requests right now. Wait a few seconds, then try again.", "retry")
    if isinstance(exc, sdk.APIStatusError):
        if exc.status_code >= 500:
            message = f"{name} is having trouble right now (error {exc.status_code}). Try again in a moment."
            return BrainError(message, "retry")
        return BrainError(f"{name} returned an error ({exc.status_code}): {msg[:200]}")
    if isinstance(exc, sdk.APIConnectionError):
        return BrainError(f"Couldn't reach {name}. Check your internet connection, then try again.", "retry")
    return BrainError("The answer was interrupted. Try again.", "retry")  # an error event mid-stream
