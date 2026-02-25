"""Tests for adapter resolution and mode/adapter separation."""

from evalkit.adapters.http_app import HttpAppAdapter
from evalkit.adapters.offline_stub import OfflineStubAdapter
from evalkit.adapters.anthropic_messages import AnthropicMessagesAdapter
from evalkit.runners.runner import resolve_adapter


def test_offline_mode_default_is_stub():
    adapter = resolve_adapter("", "offline")
    assert isinstance(adapter, OfflineStubAdapter)


def test_offline_mode_legacy_name_is_stub():
    adapter = resolve_adapter("offline", "offline")
    assert isinstance(adapter, OfflineStubAdapter)


def test_online_mode_default_is_anthropic():
    adapter = resolve_adapter("", "online")
    assert isinstance(adapter, AnthropicMessagesAdapter)


def test_explicit_http_in_offline_mode():
    """MODE=offline + adapter=http should still return HttpAppAdapter."""
    adapter = resolve_adapter("http", "offline")
    assert isinstance(adapter, HttpAppAdapter)


def test_explicit_http_in_online_mode():
    adapter = resolve_adapter("http", "online")
    assert isinstance(adapter, HttpAppAdapter)


def test_explicit_anthropic_in_offline_mode():
    adapter = resolve_adapter("anthropic", "offline")
    assert isinstance(adapter, AnthropicMessagesAdapter)


def test_explicit_offline_stub():
    adapter = resolve_adapter("offline_stub", "online")
    assert isinstance(adapter, OfflineStubAdapter)


def test_unknown_adapter_falls_back_to_stub():
    adapter = resolve_adapter("nonexistent", "offline")
    assert isinstance(adapter, OfflineStubAdapter)
