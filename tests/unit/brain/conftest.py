"""Fixtures for the brain tests."""
import pytest
from helpers import make_snapshot

from marginalia.capture import prepare


@pytest.fixture
def prep():
    """A prepared 2x Retina screen, as the brain receives it."""
    return prepare(make_snapshot())
