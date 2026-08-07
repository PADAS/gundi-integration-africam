---
title: Tutorial — Set Up the Africam Connection
---

# Set up the Africam connection

This tutorial walks you through connecting one or more EarthRanger sites to
Africam in the Gundi portal, so that new wildlife sighting reports get an
Africam gallery link attached automatically — within about a minute of being
reported.

Everything here is point-and-click in the Gundi portal. You do not need to
write code or call APIs.

[← Overview](index.md)

---

## Prerequisites

| You need | Where it comes from |
|---|---|
| A Gundi portal account in your organisation | [gundiservice.org](https://gundiservice.org) |
| An EarthRanger site and an API token for it | Your EarthRanger admin |
| An Africam API bearer token | The Africam team |

The EarthRanger token must be allowed to **read and update events** — the
runner both fetches events and patches the gallery URL back onto them.

## Step 1 — Create the EarthRanger integration

In the Gundi portal, create (or reuse) an **EarthRanger** integration for
your site:

1. Set its **base URL** to the site, e.g. `https://yoursite.pamdas.org`.
2. In its **Authentication** action, set the **token** to your EarthRanger
   API token.

The Africam runner reads exactly these two values at runtime — if the token
is missing here, every run fails with *"No auth configuration found"* (see
[Troubleshooting](troubleshooting.md#the-run-fails-before-fetching-anything)).

## Step 2 — Create the connection

Create a new connection with:

- **Provider:** an integration of type **Africam** (this runner).
- **Destination(s):** the EarthRanger integration(s) from Step 1. Every
  EarthRanger destination you add is processed on every run, each with its
  own bookkeeping — you can fan one Africam configuration out to several
  sites.

## Step 3 — Configure the `process_new_events` action

Open the Africam integration's **Process New Events** action and fill in:

1. **Africam API Token** — the bearer token from the Africam team.
2. **Event Types** — the EarthRanger event-type slugs to forward. The
   default is `wildlife_sighting`. Slugs must exist on the EarthRanger
   site(s); a typo here shows up as a warning in the Activity Log rather
   than an error.
3. **Lookback Hours** — how far back the *first* run reaches (default 1,
   max 168). After the first run the action always continues from where it
   left off.
4. Leave **Africam API URL** and **Africam Event URL Template** at their
   defaults unless the Africam team tells you otherwise.

Save the configuration. The action runs automatically every minute — there
is nothing to start.

## Step 4 — Verify the first run

Open the connection's **Activity Log** in the Gundi portal. Within a couple
of minutes you should see:

- *"Fetching EarthRanger events from https://yoursite.pamdas.org updated
  since …"* — one such line per EarthRanger site on the connection, then
- *"Forwarded N event(s) to Africam (0 error(s))"* — a single summary for
  the run, aggregated across all of the connection's sites.

If instead you see a warning like *"Configured event type(s) not found …"*,
one of your event-type slugs doesn't exist on that site — see
[Troubleshooting](troubleshooting.md#configured-event-types-not-found).

## Step 5 — Confirm the gallery URL in EarthRanger

Report (or update) an event of a configured type on the EarthRanger site,
wait a minute, then open the event in EarthRanger. Its details should now
contain an **`africam_event_url`** field, e.g.:

```
https://ranger-media.africam.com/gallery/e0577b3a-0542-4af4-b1df-b23a9f1583ea
```

Open it — you should land on the Africam gallery for that event. That's the
whole pipeline working end-to-end.

## Next

- [**Configuration**](configuration.md) — what each setting does, and how
  the incremental fetch window works.
- [**Troubleshooting**](troubleshooting.md) — if any step above didn't look
  like this.
