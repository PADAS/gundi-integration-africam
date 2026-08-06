# MkDocs GitHub Pages Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a public MkDocs documentation site for gundi-integration-africam at `https://padas.github.io/gundi-integration-africam/`, mirroring the gundi-integration-cmore setup.

**Architecture:** Four curated Markdown pages under `docs/` built by MkDocs with the Material theme; a GitHub Actions workflow validates every PR with `mkdocs build --strict` and deploys to the `gh-pages` branch via `mkdocs gh-deploy` on pushes to main. Non-curated files in `docs/` (Postman collection, superpowers specs/plans) are excluded from the build.

**Tech Stack:** MkDocs + mkdocs-material 9.7.6, GitHub Actions, GitHub Pages (deploy-from-branch).

**Spec:** `docs/superpowers/specs/2026-08-06-mkdocs-github-pages-design.md`

## Global Constraints

- The repo is **public**: nothing under `docs/` may contain a real credential. The Postman collection must be sanitized (Task 1) before any push.
- Pin `mkdocs-material==9.7.6` everywhere (CI and local verification) — same version as gundi-integration-cmore.
- All builds run with `--strict`; broken internal links and nav mismatches are failures.
- Docs describe the code as it is on `main` today: action id `process_new_events`, crontab `* * * * *`, all EarthRanger destinations processed with per-destination Redis state.
- Working directory for all commands: `/Users/chrisdo/padas/gundi-integration-africam`.
- Do not commit `site/` (build output) — it is already covered by `.gitignore`'s handling in cmore; verify before committing and add `site/` to `.gitignore` if absent.

---

### Task 1: Sanitize the Postman collection

The untracked `docs/Africam - EarthRanger Webhook.postman_collection.json` contains a real Africam bearer token (`REDACTED_AFRICAM_TOKEN`) in **two** places: `item[0].request.auth.bearer[0].value` and the collection-level `auth.bearer[0].value`. Replace both with a Postman variable and declare the variable so the collection still works when a user fills it in.

**Files:**
- Modify: `docs/Africam - EarthRanger Webhook.postman_collection.json`

**Interfaces:**
- Produces: a secret-free JSON file that later tasks can safely commit and that `mkdocs.yml` (Task 3) excludes from the built site via `*.json`.

- [ ] **Step 1: Verify the token is present (the "failing test")**

Run:
```bash
grep -c "REDACTED_AFRICAM_TOKEN" "docs/Africam - EarthRanger Webhook.postman_collection.json"
```
Expected: `2`

- [ ] **Step 2: Replace both token values and declare the variable**

Edit the JSON: change both `"value": "REDACTED_AFRICAM_TOKEN"` occurrences to `"value": "{{africam_token}}"`, and add a top-level `variable` array after the `auth` block:

```json
 "variable": [
  {
   "key": "africam_token",
   "value": "",
   "type": "string"
  }
 ],
```

(Keep the rest of the file byte-identical; it must remain valid Postman v2.1 JSON.)

- [ ] **Step 3: Verify the token is gone and the JSON is valid**

Run:
```bash
grep -c "REDACTED_AFRICAM_TOKEN" "docs/Africam - EarthRanger Webhook.postman_collection.json" || echo "token gone"
python3 -c "import json; d=json.load(open('docs/Africam - EarthRanger Webhook.postman_collection.json')); assert d['auth']['bearer'][0]['value']=='{{africam_token}}'; assert d['item'][0]['request']['auth']['bearer'][0]['value']=='{{africam_token}}'; print('OK')"
```
Expected: `token gone` and `OK`

- [ ] **Step 4: Commit**

```bash
git add "docs/Africam - EarthRanger Webhook.postman_collection.json"
git commit -m "docs: add sanitized Postman collection for the Africam webhook"
```

---

### Task 2: Write the four documentation pages

Create the curated pages. No build tooling yet (that's Task 3), so verification here is content-level: files exist, internal links reference files that exist, and no secrets appear.

**Files:**
- Create: `docs/index.md`
- Create: `docs/tutorial-setup.md`
- Create: `docs/configuration.md`
- Create: `docs/troubleshooting.md`

**Interfaces:**
- Produces: the four pages `mkdocs.yml`'s nav (Task 3) references, in this order: `index.md`, `tutorial-setup.md`, `configuration.md`, `troubleshooting.md`. Internal links between pages use plain relative Markdown links (`configuration.md`, `troubleshooting.md#...`), which MkDocs validates under `--strict`.

- [ ] **Step 1: Write `docs/index.md`**

````markdown
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
````

- [ ] **Step 2: Write `docs/tutorial-setup.md`**

````markdown
---
title: Tutorial — Set Up the Africam Connection
---

# Set up the Africam connection

This tutorial walks you through connecting one or more EarthRanger sites to
Africam in the Gundi portal, so that new wildlife-sighting reports get an
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
of minutes you should see, per EarthRanger site:

- *"Fetching EarthRanger events from https://yoursite.pamdas.org updated
  since …"*, then
- *"Forwarded N event(s) to Africam (0 error(s))"*.

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
````

- [ ] **Step 3: Write `docs/configuration.md`**

````markdown
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
````

- [ ] **Step 4: Write `docs/troubleshooting.md`**

````markdown
---
title: Troubleshooting
---

# Troubleshooting

Common symptoms when gallery URLs don't show up in EarthRanger, and how to
diagnose them. Start with the connection's **Activity Log** in the Gundi
portal — every run logs what it fetched and forwarded there. For deeper
digging, the runner's Cloud Run logs:

```bash
gcloud run services logs read africam-actions-runner \
  --project=<project> --region=us-central1 --limit=100
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
- Two consecutive log lines *"Fetching EarthRanger events ..."* with no
  *"Forwarded ..."* summary in between means the run crashed mid-way — the
  stack trace is in the Cloud Run logs.

[← Overview](index.md) · [Configuration](configuration.md)
````

- [ ] **Step 5: Verify pages and links**

Run:
```bash
ls docs/index.md docs/tutorial-setup.md docs/configuration.md docs/troubleshooting.md
grep -o '](\([a-z-]*\.md\)' docs/*.md | sort -u
grep -ri "REDACTED_AFRICAM_TOKEN" docs/*.md || echo "no secrets"
```
Expected: all four files listed; every linked `.md` target is one of the four files; `no secrets`.

- [ ] **Step 6: Commit**

```bash
git add docs/index.md docs/tutorial-setup.md docs/configuration.md docs/troubleshooting.md
git commit -m "docs: add mkdocs site pages (overview, tutorial, configuration, troubleshooting)"
```

---

### Task 3: Add mkdocs.yml and verify a strict local build

**Files:**
- Create: `mkdocs.yml`
- Modify: `.gitignore` (add `site/` if not already ignored)

**Interfaces:**
- Consumes: the four pages from Task 2 (exact filenames in nav).
- Produces: `mkdocs.yml` at the repo root — the workflow in Task 4 runs `mkdocs build --strict` and `mkdocs gh-deploy` against it.

- [ ] **Step 1: Verify the build fails without config (the "failing test")**

Run:
```bash
pip install mkdocs-material==9.7.6
mkdocs build --strict 2>&1 | tail -1
```
Expected: error — no `mkdocs.yml` config file found.

- [ ] **Step 2: Write `mkdocs.yml`**

```yaml
site_name: Gundi Africam Action Runner
site_description: What the Africam action runner does and how to configure it.
repo_url: https://github.com/PADAS/gundi-integration-africam
repo_name: PADAS/gundi-integration-africam

theme:
  name: material
  palette:
    - scheme: default
      primary: green
      accent: green
  features:
    - navigation.top
    - content.code.copy
    - toc.integrate

nav:
  - Overview: index.md
  - Tutorial — Set Up the Africam Connection: tutorial-setup.md
  - Configuration: configuration.md
  - Troubleshooting: troubleshooting.md

markdown_extensions:
  - admonition
  - tables
  - pymdownx.superfences
  - toc:
      permalink: true

# docs_dir defaults to docs/. That folder also holds the Postman collection
# and superpowers specs/plans — exclude them so only the curated pages are
# built (the repo is public).
exclude_docs: |
  *.json
  superpowers/
```

- [ ] **Step 3: Verify the strict build passes**

Run:
```bash
mkdocs build --strict
ls site/index.html site/tutorial-setup/index.html site/configuration/index.html site/troubleshooting/index.html
ls site/superpowers 2>&1 || echo "superpowers excluded OK"
```
Expected: build succeeds with no warnings; the four page outputs exist; `superpowers excluded OK`.

- [ ] **Step 4: Ensure `site/` is git-ignored**

Run:
```bash
grep -qx 'site/' .gitignore || echo 'site/' >> .gitignore
git status --short | grep -v '^??.*site/' | head
```
Expected: `site/` present in `.gitignore`; `git status` shows no `site/` entries.

- [ ] **Step 5: Commit**

```bash
git add mkdocs.yml .gitignore
git commit -m "docs: add mkdocs config (material theme, strict-buildable nav)"
```

---

### Task 4: Add the docs deploy workflow

**Files:**
- Create: `.github/workflows/docs.yml`

**Interfaces:**
- Consumes: `mkdocs.yml` from Task 3.
- Produces: on push to main, a `gh-pages` branch that Task 5 points GitHub Pages at.

- [ ] **Step 1: Write `.github/workflows/docs.yml`** (copied from gundi-integration-cmore unchanged)

```yaml
name: docs

on:
  push:
    branches: [main]
    paths: ['docs/**', 'mkdocs.yml', '.github/workflows/docs.yml']
  pull_request:
    paths: ['docs/**', 'mkdocs.yml', '.github/workflows/docs.yml']
  # Allow manual triggers from the Actions UI.
  workflow_dispatch:

# gh-deploy commits the built site to the gh-pages branch.
permissions:
  contents: write

# Serialize deploys so two pushes to main in quick succession don't race on
# gh-deploy --force.
concurrency:
  group: docs-deploy
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # gh-deploy needs full history to commit to gh-pages.
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install mkdocs-material==9.7.6
      # --strict catches broken internal links and pages missing from the nav.
      # Runs on PRs too (validation); the deploy step below is gated to main.
      - name: Build site
        run: mkdocs build --strict
      # Publishes to the gh-pages branch (Pages source: Deploy from a branch),
      # matching gundi-client / earthranger-smart-utils.
      - name: Deploy to gh-pages
        if: github.ref == 'refs/heads/main'
        run: mkdocs gh-deploy --force
```

- [ ] **Step 2: Validate the YAML parses**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "ci: build and deploy mkdocs site to gh-pages"
```

---

### Task 5: Push, deploy, and configure GitHub Pages

This task pushes to `main` on the public repo — everything committed so far
goes live. Re-verify no secrets first.

**Files:**
- None (remote operations only).

**Interfaces:**
- Consumes: all commits from Tasks 1–4; the `docs` workflow.
- Produces: the live site at `https://padas.github.io/gundi-integration-africam/`.

- [ ] **Step 1: Final secret sweep, then push**

Run:
```bash
git log origin/main..HEAD --oneline
git diff origin/main..HEAD | grep -i "REDACTED_AFRICAM_TOKEN" || echo "clean"
git push origin main
```
Expected: the docs commits listed; `clean`; push succeeds.

- [ ] **Step 2: Watch the workflow run**

Run:
```bash
gh run watch --repo PADAS/gundi-integration-africam $(gh run list --repo PADAS/gundi-integration-africam --workflow=docs --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: the `docs` workflow completes successfully (build + gh-deploy steps green). The `gh-pages` branch now exists.

- [ ] **Step 3: Point GitHub Pages at gh-pages**

Run:
```bash
gh api -X POST repos/PADAS/gundi-integration-africam/pages \
  -F "source[branch]=gh-pages" -F "source[path]=/" 2>/dev/null \
  || gh api -X PUT repos/PADAS/gundi-integration-africam/pages \
  -F "source[branch]=gh-pages" -F "source[path]=/"
gh api repos/PADAS/gundi-integration-africam/pages --jq '.html_url, .source.branch'
```
Expected: `https://padas.github.io/gundi-integration-africam/` and `gh-pages`.

- [ ] **Step 4: Verify the live site**

Run (Pages can take a minute or two on first publish; retry if 404):
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://padas.github.io/gundi-integration-africam/
curl -s https://padas.github.io/gundi-integration-africam/ | grep -o "<title>[^<]*" | head -1
```
Expected: `200` and a title containing `Gundi Africam Action Runner`.
