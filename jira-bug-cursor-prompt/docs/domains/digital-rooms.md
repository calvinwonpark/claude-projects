# Digital Rooms — Domain Knowledge

## Overview

Digital Rooms are shareable, branded micro-sites that bundle pitch decks, documents, and analytics into a single link. They are the primary content delivery mechanism for external stakeholders (investors, partners, prospects).

## Architecture

- **room-content-api** — Serves room layouts and resolves content references. Runs as a Node.js service behind the API gateway.
- **PitchContentRenderer** — React component that hydrates pitch slide data into the room content panel. Receives `pitchData` prop from the room page loader.
- **ExternalRequestMiddleware** — Express middleware that sanitizes requests from external (unauthenticated) share links. Strips certain headers before proxying to downstream services for security.

## Key Data Flows

1. Room page load → `room-content-api` resolves room config → fetches linked pitch data from `pitch-data-service` → returns hydrated payload to frontend.
2. External share flow adds an additional auth layer: external tokens are issued with scoped permissions (`room:view`, `pitch:read`).

## Common Bug Patterns

- **Blank content on external share**: Usually caused by the `ExternalRequestMiddleware` stripping auth headers needed by downstream services. Verify that the middleware allowlists the target service.
- **Stale room content**: Room config is cached with a 5-minute TTL. Edits may not appear immediately — check cache invalidation.
- **Permission errors for linked content**: External tokens may lack required scopes. Verify token generation includes all needed scopes (`pitch:read`, `doc:read`).

## Related Services

- `pitch-data-service` — Serves pitch deck content and slide data.
- `auth-service` — Generates external share tokens.
- `analytics-service` — Tracks room views and engagement.

## Debugging Tips

- Always check `ExternalRequestMiddleware` configuration when external-only issues are reported.
- Verify room-to-pitch linkage in the room config object before assuming a rendering bug.
- Check the pitch data hydration response payload — external vs. internal payloads can differ.
- Look at service-to-service auth patterns. The `analytics-service` integration (DR-891) is a good reference for how external auth should be forwarded.
