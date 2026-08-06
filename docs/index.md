---
title: Overview
---

# Gundi Africam Action Runner

This is a [Gundi](https://gundiservice.org) **action runner** for
[Africam](https://africam.com). It pulls events from one or more
**EarthRanger** sites, forwards matching event types to the Africam API, and
writes the resulting Africam **gallery URL** back onto each EarthRanger event
— so rangers can click straight from an EarthRanger report to the Africam
media gallery for that sighting.

It's a single Cloud Run service that handles **all** customer integrations of
type `africam`: each customer's connection is configured in the Gundi portal,
and this runner processes every EarthRanger destination on that connection.

## What it does

Every minute (crontab `* * * * *`), for each EarthRanger site on the
connection, the `process_new_events` action:

1. Fetches events **updated since the last run** (first run looks back
   `lookback_hours`).
2. Keeps only the configured **event types** (e.g. `wildlife_sighting`) and
   skips events that already carry an `africam_event_url` (already
   processed — the action is idempotent).
3. POSTs each remaining event to Africam's webhook
   (`POST {africam_api_url}/events/webhook`).
4. Builds a gallery URL from the `eventId` Africam returns and **patches it
   into the EarthRanger event's details** as `africam_event_url`.

A failure on one event is logged and doesn't stop the rest of the batch.

## Where it sits

```
EarthRanger site(s) ◄──── pull events / patch gallery URL ────┐
                                                              │
                                              Africam action runner (this service)
                                                              │
                                                              └────► Africam API
                                                                     POST /events/webhook
```

Unlike most Gundi integrations, this runner does **not** route data through
Gundi's delivery pipeline — it talks to EarthRanger and Africam directly. The
Gundi portal is where the pieces are wired together: the **connection** holds
this Africam integration plus one or more **EarthRanger destination
integrations**, whose base URL and API token the runner reads at runtime (see
[Configuration](configuration.md)).

## Next

- [**Tutorial: set up the Africam connection**](tutorial-setup.md) —
  step-by-step in the Gundi portal, from creating the connection to seeing
  the first gallery URL appear in EarthRanger.
- [**Configuration**](configuration.md) — every setting on the
  `process_new_events` action, and where the EarthRanger credentials come
  from.
- [**Troubleshooting**](troubleshooting.md) — common symptoms (missing event
  types, events not forwarded, Africam errors) and how to diagnose them from
  the Activity Log.
