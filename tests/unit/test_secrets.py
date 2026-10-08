"""The API key in the OS credential store."""

from helpers import FakeKeyring

from marginalia.secrets import ACCOUNT, SERVICE, Keychain, mask


def test_round_trip():
    kr = FakeKeyring()
    kc = Keychain(kr)
    assert kc.get() is None
    assert kc.set("  sk-ant-abc  ")
    assert kr.data[(SERVICE, ACCOUNT)] == "sk-ant-abc", "pasted whitespace is trimmed"
    assert kc.get() == "sk-ant-abc"
    assert kc.delete() and kc.get() is None


def test_failures_are_reported_not_raised(caplog):
    kc = Keychain(FakeKeyring(error=RuntimeError("No recommended backend")))
    assert kc.get() is None and kc.problem == "No recommended backend"
    assert not kc.set("sk") and "Could not save the API key" in caplog.text
    assert not kc.delete()


def test_deleting_nothing_is_fine():
    assert not Keychain(FakeKeyring()).delete()


def test_missing_keyring_package_is_a_problem_not_a_crash(monkeypatch):
    import marginalia.secrets

    def missing():
        raise ImportError("No module named 'keyring'")

    monkeypatch.setattr(marginalia.secrets, "_default_backend", missing)
    kc = Keychain()
    assert kc.get() is None and "keyring" in kc.problem


def test_mask_shows_only_the_ends():
    assert mask("sk-ant-api03-abcdefghijklmnop") == "sk-ant-…mnop"
    assert mask("short") == "…" and mask(None) == ""
