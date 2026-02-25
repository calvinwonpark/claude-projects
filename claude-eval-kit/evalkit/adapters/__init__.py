"""Adapters for running evaluation cases against different backends."""

from evalkit.adapters.base import BaseAdapter
from evalkit.adapters.offline_stub import OfflineStubAdapter

__all__ = ["BaseAdapter", "OfflineStubAdapter"]
