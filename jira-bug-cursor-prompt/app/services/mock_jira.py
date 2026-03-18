from __future__ import annotations

from app.models.jira import JiraBug, JiraComment, JiraIssueFields, JiraUser

_MOCK_ISSUES: dict[str, JiraBug] = {
    "DR-1042": JiraBug(
        key="DR-1042",
        id="104201",
        self_url="https://company.atlassian.net/rest/api/3/issue/104201",
        fields=JiraIssueFields(
            summary=(
                "Digital Room page shows blank content section "
                "when pitch deck is linked via external share"
            ),
            description=(
                "## Description\n"
                "When a pitch deck is shared externally and the recipient opens the "
                "Digital Room link, the main content area renders as blank. The room "
                "chrome (header, sidebar, footer) loads correctly but the central "
                "content panel where the pitch deck should render shows nothing.\n"
                "\n"
                "## Steps to Reproduce\n"
                "1. Create a new Digital Room in the dashboard\n"
                "2. Link an existing pitch deck (e.g. 'Q4 Investor Update') to the room\n"
                "3. Enable external sharing and generate a share link\n"
                "4. Open the share link in an incognito browser window\n"
                "5. Observe the main content area\n"
                "\n"
                "## Expected Behavior\n"
                "The pitch deck content should render in the main content panel of the "
                "Digital Room, showing all slides with navigation controls.\n"
                "\n"
                "## Actual Behavior\n"
                "The content panel is completely blank. No error messages are shown to "
                "the user. The browser console shows:\n"
                "`TypeError: Cannot read properties of undefined (reading 'slides')`\n"
                "followed by `Warning: PitchContentRenderer received null pitchData prop`.\n"
                "\n"
                "## Additional Context\n"
                "- This only affects externally shared rooms. Internal (authenticated) "
                "users see the content fine.\n"
                "- The pitch data API call returns 200 but the response payload differs "
                "for external tokens.\n"
                "- Suspect the external auth token doesn't include the `pitch:read` scope.\n"
                "- Similar issue was seen in DR-891 (resolved by adding scope to external "
                "token generation).\n"
            ),
            status="Open",
            priority="High",
            issue_type="Bug",
            components=["digital-rooms", "pitch-renderer"],
            labels=["external-sharing", "pitch-data", "regression", "customer-reported"],
            environment=(
                "Production — Chrome 120, Safari 17. "
                "Reproduced in staging with external share links."
            ),
            reporter=JiraUser(
                account_id="user-001",
                display_name="Sarah Chen",
                email="sarah.chen@company.com",
            ),
            assignee=None,
            created="2026-03-14T09:23:00.000Z",
            updated="2026-03-15T14:10:00.000Z",
            comments=[
                JiraComment(
                    id="c-1",
                    author=JiraUser(
                        account_id="user-002",
                        display_name="Mike Torres",
                    ),
                    body=(
                        "I checked the external token generation in auth-service. "
                        "The `pitch:read` scope is present in the token but the "
                        "room-content-api is not forwarding the token to the "
                        "pitch-data-service when the request comes from an external "
                        "share context. It strips auth headers for external requests "
                        "as a safety measure added in v2.14."
                    ),
                    created="2026-03-14T11:45:00.000Z",
                    updated="2026-03-14T11:45:00.000Z",
                ),
                JiraComment(
                    id="c-2",
                    author=JiraUser(
                        account_id="user-003",
                        display_name="Priya Patel",
                    ),
                    body=(
                        "Confirmed — the `ExternalRequestMiddleware` in "
                        "room-content-api strips Authorization headers before "
                        "proxying to downstream services. We need to allowlist "
                        "pitch-data-service calls or use a service-to-service "
                        "token for the pitch data fetch. This is the same pattern "
                        "we used for analytics-service in DR-891."
                    ),
                    created="2026-03-15T10:30:00.000Z",
                    updated="2026-03-15T10:30:00.000Z",
                ),
            ],
        ),
    ),
}


def get_mock_bug(issue_key: str) -> JiraBug | None:
    return _MOCK_ISSUES.get(issue_key)


def list_mock_keys() -> list[str]:
    return list(_MOCK_ISSUES.keys())
