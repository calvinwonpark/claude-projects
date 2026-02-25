"""Base adapter interface."""

from __future__ import annotations

import abc

from evalkit.types import Case, Trace


class BaseAdapter(abc.ABC):
    """All adapters implement run_case to produce a Trace from a Case."""

    name: str = "base"

    @abc.abstractmethod
    async def run_case(self, case: Case, run_id: str = "") -> Trace:
        """Execute a single evaluation case and return a Trace."""
        ...
