# Debug Playbook — Digital Rooms

## Triage Checklist

1. **Reproduce the issue** — Confirm whether it affects internal users, external users, or both.
2. **Check room config** — Fetch the room config from `room-content-api` and verify all content references resolve.
3. **Verify pitch linkage** — Ensure the linked pitch ID exists and the pitch-data-service returns valid data for it.
4. **Inspect auth context** — For external share issues, verify the external token includes required scopes (`room:view`, `pitch:read`, `doc:read`).
5. **Check middleware behavior** — Review `ExternalRequestMiddleware` logs to see if auth headers are being stripped for downstream service calls.

## External Share Issues

External share bugs are the most common category. The root cause is usually one of:

- **Auth header stripping**: `ExternalRequestMiddleware` strips `Authorization` headers from external requests before proxying to downstream services. If a downstream service (like `pitch-data-service`) requires auth, the call fails silently or returns partial data.
  - **Fix pattern**: Add the downstream service to the middleware's allowlist, or use a service-to-service token for the internal hop.
  - **Reference**: DR-891 solved this for `analytics-service`.

- **Missing token scopes**: External tokens are generated with limited scopes. If a new feature requires a scope that wasn't added to external token generation, it will work for internal users but fail for external.
  - **Fix pattern**: Update `auth-service` token generation to include the required scope for external tokens.

- **Response shape differences**: `pitch-data-service` returns different response shapes for internal vs. external auth contexts. The frontend may not handle the external shape correctly.
  - **Fix pattern**: Normalize the response in the BFF layer, or make the renderer handle both shapes.

## Rendering Issues

- Always validate upstream data before debugging the React rendering layer.
- Check the `PitchContentRenderer` component props — `null` vs. `undefined` vs. empty object will cause different failure modes.
- Room chrome loading but content missing usually points to a data-fetching issue, not a rendering bug.

## Common Mistakes

- Assuming a blank page is a frontend bug — it's usually a data/auth issue.
- Fixing the symptom (adding null checks in the renderer) without fixing the root cause (auth headers not forwarded).
- Not checking the `ExternalRequestMiddleware` configuration when the issue only affects external users.
