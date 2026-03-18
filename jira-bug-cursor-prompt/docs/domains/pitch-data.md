# Pitch Data — Domain Knowledge

## Overview

The pitch data domain covers the creation, storage, and rendering of pitch decks. Pitch decks are the core content type and can be linked into Digital Rooms, shared directly, or embedded.

## Architecture

- **pitch-data-service** — Go service that stores and serves pitch content. Handles CRUD operations, versioning, and access control.
- **PitchContentRenderer** — Shared React component used across the app and Digital Rooms to render pitch slides.
- **pitch-asset-pipeline** — Async pipeline that processes uploaded assets (images, PDFs) into optimized slide content.

## Key Data Model

```
Pitch
  ├── id: string
  ├── title: string
  ├── slides: Slide[]
  ├── version: number
  ├── permissions: Permission[]
  └── metadata: PitchMetadata

Slide
  ├── id: string
  ├── order: number
  ├── content: SlideContent
  └── assets: Asset[]
```

## Common Bug Patterns

- **Null slides array**: Older pitches created before the migration may have a `null` slides field instead of an empty array. Always use defensive access (`pitch?.slides ?? []`).
- **External access returns partial data**: The `pitch-data-service` returns different response shapes depending on the auth context. External tokens get a subset of fields. Ensure the renderer handles both shapes.
- **Asset loading failures**: Assets are served from a CDN with signed URLs. If the pitch was recently updated, CDN cache may serve stale signed URLs. Check the `X-Asset-Version` header.

## Debugging Tips

- Check whether the issue reproduces with internal auth vs. external tokens — this narrows the scope significantly.
- Validate upstream pitch data before investigating frontend rendering. Use `GET /api/v2/pitches/:id?expand=slides` to inspect the full payload.
- For rendering issues, check the `PitchContentRenderer` props — specifically whether `pitchData` is null vs. an empty object vs. a valid pitch.
- Version mismatches between cached and live data are a frequent source of "ghost" bugs.
