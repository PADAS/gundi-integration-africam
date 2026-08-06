# MkDocs GitHub Pages for gundi-integration-africam — Design

**Date:** 2026-08-06
**Status:** Approved

## Goal

Publish a public documentation site for this integration at
`https://padas.github.io/gundi-integration-africam/`, mirroring the setup
already used in `gundi-integration-cmore` (and gundi-client /
earthranger-smart-utils): MkDocs with the Material theme, built and deployed
by a GitHub Actions workflow via `mkdocs gh-deploy` to the `gh-pages` branch.

## Approach

Exact mirror of the cmore pattern. Alternatives considered and rejected:

- **Native Pages Actions flow** (`actions/deploy-pages`, no `gh-pages`
  branch) — slightly more modern but diverges from the org convention for no
  benefit.
- **Manual local `mkdocs gh-deploy`** — no CI; docs silently drift from main.

## Files added

```
mkdocs.yml                      # Material theme, green palette, 4-page nav
.github/workflows/docs.yml      # strict build on PRs, gh-deploy on main
docs/index.md                   # Overview
docs/tutorial-setup.md          # Tutorial — set up the Africam connection
docs/configuration.md           # Configuration reference
docs/troubleshooting.md         # Troubleshooting
```

## mkdocs.yml

Mirrors cmore's file:

- `site_name: Gundi Africam Action Runner`
- `site_description`: what the Africam action runner does and how to
  configure it
- `repo_url: https://github.com/PADAS/gundi-integration-africam`
- Theme: `material`, default scheme, green primary/accent; features
  `navigation.top`, `content.code.copy`, `toc.integrate`
- Markdown extensions: `admonition`, `tables`, `pymdownx.superfences`,
  `toc` with `permalink: true`
- Nav: Overview → Tutorial — Set Up the Africam Connection → Configuration
  → Troubleshooting
- `exclude_docs` covering `*.json` (the Postman collection) and
  `superpowers/` (specs/plans like this one), so only the curated pages are
  built. The repo is public, so excluded files are still visible in the repo
  — they just don't appear on the site.

## GitHub Actions workflow (.github/workflows/docs.yml)

Copied from cmore unchanged — same triggers and steps:

- Triggers: push to `main` and pull requests, both path-filtered to
  `docs/**`, `mkdocs.yml`, `.github/workflows/docs.yml`; plus
  `workflow_dispatch`.
- `permissions: contents: write` (gh-deploy commits to `gh-pages`).
- `concurrency: docs-deploy`, `cancel-in-progress: false` — serialize
  deploys.
- Steps: checkout with `fetch-depth: 0`, Python 3.12,
  `pip install mkdocs-material==9.7.6`, `mkdocs build --strict` (runs on
  PRs as validation), then `mkdocs gh-deploy --force` gated to
  `github.ref == 'refs/heads/main'`.

## Page content (text-only, screenshot-ready)

All pages are written text-only for now. The tutorial is structured in
numbered steps so portal screenshots can be dropped in later without
restructuring.

### index.md — Overview

- What the integration is: a Gundi v2 action runner that pulls events from
  one or more EarthRanger sites every minute (all EarthRanger destinations
  on the connection), forwards matching event types to the Africam API, and
  patches each forwarded ER event with the resulting Africam gallery URL
  (`africam_event_url` in `event_details`).
- One Cloud Run service handles all customer integrations of this type;
  each customer gets their own configuration in the Gundi portal.
- Data-flow summary: ER events → `POST {africam_api_url}/events/webhook`
  (envelope `{"event_type": "event_update", "data": {...}}`) → Africam
  returns `eventId` → gallery URL patched back into the ER event.
- Already-processed events (those with `africam_event_url` set) are
  skipped, making the action idempotent.

### tutorial-setup.md — Tutorial

Step-by-step, text-only:

1. Create the connection in the Gundi portal (EarthRanger provider →
   Africam destination).
2. Configure the `process_new_events` action: Africam API token, event-type
   slugs to forward, lookback hours.
3. Trigger/wait for the first run and verify it in the Activity Log.
4. Confirm the `africam_event_url` appears in the ER event's details and
   opens the Africam gallery.

### configuration.md — Configuration reference

- Table of `AfricamActionConfiguration` fields (from
  `app/actions/configurations.py`): `africam_api_url`, `africam_token`
  (password widget), `event_types` (default `["wildlife_sighting"]`),
  `lookback_hours` (1–168, range widget), `africam_event_url_template`
  (must be `https://` and contain `{africam_event_id}`).
- Callout: EarthRanger credentials (`base_url`, token) are **not** in the
  action config — they are resolved at runtime from the connection's
  destination integrations' auth configs; every EarthRanger destination on
  the connection is processed, each with independent Redis state.
- The action runs on a `* * * * *` crontab; `last_execution` state is kept
  in Redis, with `lookback_hours` used only for the first run.

### troubleshooting.md — Troubleshooting

Keyed to real behaviors in `app/actions/handlers.py`:

- **Missing event types**: a configured slug that doesn't exist on the ER
  site logs a WARNING in the Activity Log (throttled to once per hour per
  destination) and is skipped; other types still process.
- **No slugs resolve**: that destination's fetch is skipped entirely and
  its state is unchanged, so the window is retried once config is fixed.
- **Per-event failures**: caught per event; one failure doesn't abort the
  batch.
- **State**: `last_execution` in Redis; how the fetch window is derived.
- **Where to look**: the Gundi portal Activity Log for start/complete/error
  events and custom warnings.

## Postman collection

`docs/Africam - EarthRanger Webhook.postman_collection.json` currently
contains a real-looking Africam bearer token and the repo is public. It is
sanitized in place — token value replaced with a `{{africam_token}}` Postman
variable (both the request-level and collection-level `auth` blocks) — then
kept in `docs/` as a useful API example, excluded from the built site via
`exclude_docs`.

## Deployment prerequisite

After the first successful workflow run creates the `gh-pages` branch,
GitHub Pages must be configured to serve from it (Settings → Pages →
Deploy from a branch → `gh-pages`; or via
`gh api repos/PADAS/gundi-integration-africam/pages`). The site then serves
at `https://padas.github.io/gundi-integration-africam/`.

## Testing

- `mkdocs build --strict` passes locally before committing (catches broken
  internal links and pages missing from the nav).
- The workflow enforces the same strict build on every PR touching docs.
- No Python-app tests are affected; no runtime code changes.
