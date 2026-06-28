"""Test compatibility helpers."""

from __future__ import annotations

from typing import cast

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError:  # pragma: no cover
    MockConfigEntry = cast(type, object)
