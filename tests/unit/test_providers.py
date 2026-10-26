"""The services and their models: friendly names for what people read."""

from marginalia.providers import model_name, provider_of_model


def test_a_listed_model_is_named_in_words():
    assert model_name("claude-opus-5-5") == "Claude Opus 5.5"
    assert model_name("gemini-3.8-flash") == "Gemini 3.8 Flash"


def test_a_model_we_do_not_list_keeps_its_id():
    assert model_name("claude-opus-4-8") == "claude-opus-4-8"
    assert provider_of_model("claude-opus-4-8") is None
