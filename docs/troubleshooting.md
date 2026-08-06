---
title: Troubleshooting
---

# Troubleshooting

Common symptoms when gallery URLs don't show up in EarthRanger, and how to
diagnose them. Start with the connection's **Activity Log** in the Gundi
portal — every run logs what it fetched and forwarded there. For deeper
digging, the runner's Cloud Run logs:

```bash
gcloud run services logs read <service> \
  --project=<project> --region=<region> --limit=100
```

[← Overview](index.md) · [Configuration](configuration.md)

---

## Configured event types not found

Activity Log warning:

```
Configured event type(s) not found on https://<site>, skipping: <slug, ...>
```

One or more **Event Types** slugs don't exist on that EarthRanger site.
Events of the *other* configured types still flow; the missing ones are
skipped. Fix the slug in the action config (or create the event type on the
ER site). The warning is throttled to **once per hour per site**, so don't
expect it on every one-minute run.

If **none** of the configured slugs exist on a site, that site's fetch is
skipped entirely (the runner never pulls unfiltered events), and its fetch
window doesn't advance — once you fix the configuration, the missed period
is picked up automatically.

## The run fails before fetching anything

Errors in the Activity Log like:

- `No destinations configured for integration <id>` — the connection has no
  destination; add the EarthRanger integration(s) to it.
- `No auth configuration found for destination integration <id>` /
  `No token in auth configuration ...` — the EarthRanger integration's
  **Authentication** action has no token. Set it there; the Africam action
  config has no EarthRanger fields by design (see
  [Configuration](configuration.md#where-the-earthranger-credentials-come-from)).

These abort the whole run (nothing is fetched from any site) and recur every
minute until fixed.

## An event never got its gallery URL

Check in order:

1. **Is its type configured?** Only events whose `event_type` is in **Event
   Types** are forwarded.
2. **Was it updated inside the fetch window?** The first run only reaches
   back `lookback_hours`. Touching the event in EarthRanger (any edit)
   updates it and gets it re-fetched on the next run.
3. **Does it already have `africam_event_url`?** Then the runner considers
   it processed and will never re-forward it. To force a re-send, delete the
   `africam_event_url` field from the event's details and edit the event so
   it re-enters the window.
4. **Did the Africam call fail?** See the next section.

## Errors talking to Africam

Each event is forwarded independently: an error on one event is logged and
counted, and the batch continues. The run summary shows it:

```
Forwarded 4 event(s) to Africam (2 error(s))
```

(logged as a WARNING when the error count is non-zero). The per-event stack
traces are in the Cloud Run logs. HTTP failures are retried automatically
with backoff (starting at ~5 s, up to 60 s) before counting as errors, so
transient Africam hiccups usually self-heal.

A `401`/`403` on every event means the **Africam API Token** is wrong or
expired.

## Africam accepted the event but no URL was written back

Runner log line:

```
Africam response for ER event <id> contained no event ID: {...}
```

Africam's webhook response had no `eventId`, so there was nothing to build
the gallery URL from. The event counts as forwarded for that run, but since
no `africam_event_url` was written, it is re-sent the next time it falls
inside the fetch window (e.g. after any edit). If this persists,
raise it with the Africam team: their `POST /events/webhook` should return
`{"status": "updated", "eventId": "<uuid>"}`.

## The gallery URL is malformed

The URL is built from **Africam Event URL Template** by substituting
`{africam_event_id}`. The template is validated when you save the config
(must be `https://` and contain the placeholder), so a malformed URL in
EarthRanger usually means the template was pointed at the wrong path —
compare it with the default in
[Configuration](configuration.md#action-settings).

## Nothing at all happens

- The action is on a one-minute crontab — there is no manual trigger to
  forget. If the Activity Log shows no runs at all, the integration may be
  disabled, or the runner isn't deployed/registered; check the Cloud Run
  service.
- A run logs one *"Fetching EarthRanger events ..."* line per site,
  followed by a single aggregated *"Forwarded ..."* summary for the whole
  run. A run whose *"Fetching ..."* line(s) are never followed by a
  *"Forwarded ..."* summary means it crashed mid-way — the stack trace is
  in the Cloud Run logs.

[← Overview](index.md) · [Configuration](configuration.md)
