"""Maps domain IDs to their knowledge doc paths (relative to project root).

Add new domains by creating entries here and the corresponding markdown files.
"""

from __future__ import annotations

DOMAIN_DOC_MAP: dict[str, list[str]] = {
    "digital-rooms": [
        "docs/domains/digital-rooms.md",
        "docs/debug-playbooks/digital-rooms.md",
    ],
    "pitch-data": [
        "docs/domains/pitch-data.md",
    ],
}
