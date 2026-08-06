---
title: Configuration
---

# Configuring the Africam integration

All settings live on the **Africam integration's** single action,
**`process_new_events`**, configured in the Gundi portal. The action runs on
a `* * * * *` crontab — once a minute, automatically.

[← Overview](index.md)

---

## Action settings

| Field | Required | Default | Description |
|---|---|---|---|
| **Africam API URL** | — | `https://ranger-media.africam.com` | Base URL of the Africam API. Events are POSTed to `{url}/events/webhook`. |
| **Africam API Token** | yes | — | Bearer token for Africam. Stored as a secret (password field). |
| **Event Types** | — | `wildlife_sighting` | EarthRanger event-type slugs to forward. Anything not in this list is ignored. |
| **Lookback Hours** | — | `1` (1–168) | How far back the **first** run fetches. Ignored once the action has run, because the window then continues from the previous run. |
| **Africam Event URL Template** | — | `https://ranger-media.africam.com/gallery/{africam_event_id}` | Format string for the gallery URL written back to EarthRanger. Must start with `https://` and contain `{africam_event_id}` — both are validated when you save. |

## Where the EarthRanger credentials come from

EarthRanger access is **not** configured on this action. At runtime the
runner reads the connection's **destination integrations**: each one's
**base URL** plus the **token** from its **Authentication** action config.
Every EarthRanger destination on the connection is processed on every run.

> If the connection has no destinations, or a destination has no token in
> its auth config, the whole run fails — see
> [Troubleshooting](troubleshooting.md#the-run-fails-before-fetching-anything).

## The incremental fetch window

Each EarthRanger destination keeps its own `last_execution` timestamp in the
runner's Redis state (keyed by the destination's base URL):

- **First run** (no state yet): fetch events updated in the last
  `lookback_hours`.
- **Every later run**: fetch events updated since the previous run started.

Because the filter is *updated since*, edits to older events re-fetch them —
and the already-processed check (below) keeps them from being re-forwarded.

## What gets forwarded, exactly

From each fetched event, the runner keeps only events whose type is in
**Event Types** and which do **not** already have `africam_event_url` in
their details, then POSTs to `POST {africam_api_url}/events/webhook`:

```json
{
  "event_type": "event_update",
  "data": {
    "id": "<er-event-id>",
    "event_type": "wildlife_sighting",
    "title": "...",
    "location": {"latitude": -1.4061, "longitude": 35.1425},
    "event_details": {"species": "white rhino", "count": 3}
  }
}
```

Africam replies with `{"status": "updated", "eventId": "<uuid>"}`. The
runner formats **Africam Event URL Template** with that `eventId` and
patches the EarthRanger event's details:

```json
{"event_details": {"...existing details...": "...", "africam_event_url": "https://ranger-media.africam.com/gallery/<uuid>"}}
```

> A sanitized [Postman collection](https://github.com/PADAS/gundi-integration-africam/blob/main/docs/Africam%20-%20EarthRanger%20Webhook.postman_collection.json)
> with this exact request lives in the repo — handy for testing the Africam
> endpoint with your own token.

## Event-type slugs are resolved per site

The EarthRanger API filters events by event-type **ID**, not slug, so each
run resolves your configured slugs to IDs per site. A slug that doesn't
exist on a site is **skipped with a warning** (throttled to once an hour per
site); if **none** of your slugs exist on a site, that site's fetch is
skipped entirely — the runner never falls back to fetching *all* events.

[← Overview](index.md) · [Troubleshooting](troubleshooting.md)
