from __future__ import annotations

from app import config
from app.models.jira import JiraBug
from app.services.mock_jira import get_mock_bug, list_mock_keys


async def get_jira_bug(issue_key: str) -> JiraBug:
    if config.USE_MOCK_JIRA:
        bug = get_mock_bug(issue_key)
        if bug is None:
            available = ", ".join(list_mock_keys())
            raise ValueError(
                f'Mock issue "{issue_key}" not found. Available keys: {available}'
            )
        return bug

    # Placeholder for real Jira REST / MCP integration.
    raise NotImplementedError(
        "Live Jira integration not implemented. "
        "Set USE_MOCK_JIRA=true or implement the live adapter."
    )
