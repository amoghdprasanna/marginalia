"""The model services Marginalia can ask: what each is called, where its key lives, its models.

Pure data, so config, the keychain, the Settings window and the setup check all read the same
table (ADR 0027). How each one is called lives in `brain/`.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str  # the value of the `provider` setting
    name: str  # what the user sees: in Settings, the setup check, error messages
    env: str  # environment variable that holds the API key (it wins over the keychain)
    account: str  # keychain account for the key
    module: str  # the SDK to import; missing means the extra isn't installed
    extra: str | None  # pip extra that installs the SDK (None: a core dependency)
    key_hint: str  # placeholder for the key field
    console: str  # where to create a key
    # (model id, friendly name, what it trades). The first is the default.
    models: tuple[tuple[str, str, str], ...]

    @property
    def default_model(self) -> str:
        return self.models[0][0]

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(m[0] for m in self.models)

    def installed(self) -> bool:
        try:
            return importlib.util.find_spec(self.module) is not None
        except (ImportError, ValueError):  # a parent package missing, or a broken install
            return False

    def install_hint(self) -> str:
        return f'pip install "marginalia[{self.extra}]"' if self.extra else "pip install marginalia"


PROVIDERS: dict[str, Provider] = {
    p.key: p
    for p in (
        Provider(
            key="anthropic",
            name="Claude",
            env="ANTHROPIC_API_KEY",
            account="anthropic-api-key",  # the name it had before there were others (ADR 0016)
            module="anthropic",
            extra=None,
            key_hint="Paste a key that starts with sk-ant-",
            console="https://console.anthropic.com/settings/keys",
            models=(
                ("claude-opus-5-5", "Claude Opus 5.5", "Best answers. The default."),
                ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Faster, about half the price."),
                ("claude-haiku-5-5", "Claude Haiku 5.5", "Fastest and cheapest; fine for quick definitions."),
                ("claude-fable-5-1", "Claude Fable 5.1", "Most capable; slower and pricier."),
            ),
        ),
        Provider(
            key="openai",
            # Not "ChatGPT": a ChatGPT subscription doesn't include API access, and the key is OpenAI's.
            name="OpenAI",
            env="OPENAI_API_KEY",
            account="openai-api-key",
            module="openai",
            extra="openai",
            key_hint="Paste a key that starts with sk-",
            console="https://platform.openai.com/api-keys",
            models=(
                ("gpt-6-astra", "GPT-6 Astra", "OpenAI's flagship. Best answers."),
                ("gpt-6.1-sol", "GPT-6.1 Sol", "Nearly as good, and cheaper."),
                ("gpt-6-luna", "GPT-6 Luna", "Fastest and cheapest."),
            ),
        ),
        Provider(
            key="gemini",
            name="Gemini",
            env="GEMINI_API_KEY",
            account="gemini-api-key",
            module="google.genai",
            extra="gemini",
            key_hint="Paste a key from Google AI Studio",
            console="https://aistudio.google.com/apikey",
            models=(
                ("gemini-4-argon", "Gemini 4 Argon", "Google's flagship. Best answers."),
                ("gemini-3.8-flash", "Gemini 3.8 Flash", "Faster and cheaper."),
                ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "Fastest and cheapest."),
            ),
        ),
    )
}
DEFAULT_PROVIDER = "anthropic"


def provider_of_model(model: str) -> str | None:
    """Which provider lists this model, or None for a model we don't know (any name is allowed)."""
    return next((p.key for p in PROVIDERS.values() if model in p.model_ids), None)
