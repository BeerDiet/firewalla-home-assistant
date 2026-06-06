"""Shared pytest fixtures for Firewalla tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations) -> None:
    """Enable loading integrations from this repository."""
    yield
