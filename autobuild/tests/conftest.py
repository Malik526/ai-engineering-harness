"""Shared fixtures."""

import pytest

from autobuild.providers import provider_registry
from fake_provider import TEST_REGISTRY


@pytest.fixture
def fake_registry(monkeypatch):
    """Replace the provider registry with fake providers for runner tests."""
    monkeypatch.setattr(provider_registry, "load_registry", lambda: TEST_REGISTRY)
    return TEST_REGISTRY
