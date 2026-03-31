# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Gundi v2 integration for Africam — a FastAPI service that pulls events from an EarthRanger site and forwards matching ones to the Africam API, then patches each forwarded EarthRanger event with the resulting Africam gallery URL. Also supports the standard Gundi webhook and push-data patterns if needed in future.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run a single test
pytest app/actions/tests/test_handlers.py::test_pull_events_forwards_matching_events -v

# Run with coverage output
pytest --tb=short -v

# Start local server
uvicorn app.main:app --reload --port 8080

# Recompile requirements (after editing requirements.in)
pip-compile --output-file=requirements.txt requirements-base.in requirements-dev.in requirements.in

# Local Docker dev (API docs at http://localhost:8080/docs)
cd local && docker compose up --build

# Register integration with Gundi manually
python app/register.py --slug <slug> --service-url <url>
```

## Architecture

### Africam-specific logic

| File | Purpose |
|------|---------|
| `app/actions/handlers.py` | `action_process_new_events` — the main action handler (runs every minute) |
| `app/actions/configurations.py` | `AfricamActionConfiguration` — action config model |
| `app/services/earthranger.py` | EarthRanger client (`get_events`, `patch_event`) using `AsyncERClient` |
| `app/services/africam.py` | Africam client (`post_event`) — POSTs to `/events/webhook` |
| `app/services/gundi.py` | Adds `get_er_credentials_from_destination` alongside the standard send helpers |

### Action flow: `action_process_new_events`

Runs on a `* * * * *` crontab (every minute). For each execution:

1. Calls `get_er_credentials_from_destination(integration_id)` to resolve the EarthRanger `base_url` and bearer token from the connection's first destination (via `GundiClient.get_connection_details` → `get_integration_details` → `auth` config).
2. Reads `last_execution` from Redis state; falls back to `now - lookback_hours` on first run.
3. Fetches EarthRanger events via `AsyncERClient.get_events(updated_since=..., event_type=<ids>)`.
   Event-type slugs (e.g. `wildlife_sighting`) are resolved to UUIDs first via `AsyncERClient.get_event_type(slug, version="v2.0")` — the ER API requires IDs, not slugs.
4. Skips events whose `event_details` already contain `africam_event_url` (already processed).
5. POSTs each remaining event to `POST {africam_api_url}/events/webhook` with a `{"event_type": "event_update", "data": {...}}` envelope. Africam returns `{"status": "updated", "eventId": "<uuid>"}`.
6. Builds the Africam gallery URL from `africam_event_url_template.format(africam_event_id=...)` and PATCHes it into the EarthRanger event's `event_details` as `africam_event_url`. Per-event errors are caught so one failure doesn't abort the batch.
7. Saves `last_execution` to Redis state.

### `AfricamActionConfiguration` fields

| Field | Default | Notes |
|-------|---------|-------|
| `africam_api_url` | `https://ranger-media.africam.com` | Africam base URL |
| `africam_token` | required | Bearer token; rendered as password widget |
| `event_types` | `["wildlife_sighting"]` | ER event-type slugs to forward |
| `lookback_hours` | `1` | Initial fetch window (1–168 h); range widget |
| `africam_event_url_template` | `https://ranger-media.africam.com/gallery/{africam_event_id}` | Must be `https://` and contain `{africam_event_id}`; validated via `regex` (emits `pattern` in JSON schema for browser validation) and a `@validator` that checks format-string correctness |

EarthRanger credentials (`base_url`, token) are **not** in the action config — they are read from the connection's destination integration at runtime.

### Framework patterns (unchanged from template)

**Webhooks** (`POST /webhooks`):
1. `app/routers/webhooks.py` → `app/services/webhooks.py::process_webhook()`
2. Integration resolved from `x-consumer-username` header (Kong), `x-gundi-integration-id` header, or `integration_id` query param
3. `app/webhooks/core.py::get_webhook_handler()` introspects type annotations on `webhook_handler` to determine payload and config models
4. If `GenericJsonPayload` + `DynamicSchemaConfig`: Pydantic model built at runtime from JSON schema in Gundi portal
5. If `GenericJsonTransformConfig`: JQ filter applied, routes to `obv` or `ev`
6. Transformed data forwarded via `app/services/gundi.py`

**Push data** (`POST /push-data`): PubSub-triggered, dispatches by `event_type` to handlers annotated with `PushActionConfiguration`.

### Config caching

`IntegrationConfigurationManager` (`app/services/config_manager.py`) uses Redis to cache integration and action configs. TTL is 60s for webhook configs; action configs use `None` (indefinite, invalidated via config-events).

### Activity logging

- `@activity_logger()` — logs start/complete/error events to PubSub automatically
- `await log_action_activity(...)` — custom messages visible in the Gundi portal

### UI schema customization

Use `FieldWithUIOptions(...)` with `UIOptions(widget=...)` and `GlobalUISchemaOptions(order=[...])` in config models to control field rendering in the Gundi portal (react-jsonschema-form). Adding `regex=` to a field emits a `pattern` into the JSON schema, enabling browser-side validation.

## Testing

Tests use `pytest-asyncio` and `pytest-mock`. Framework-level tests are in `app/services/tests/`; Africam-specific tests are in:

- `app/actions/tests/test_handlers.py` — handler behaviour, config validation, URL template validator
- `app/services/tests/test_earthranger.py` — slug-to-ID resolution, pagination, patch delegation

When testing the handler, mock `app.actions.handlers.get_er_credentials_from_destination`, `app.actions.handlers.get_events`, `app.actions.handlers.post_event_to_africam`, `app.actions.handlers.patch_event`, `app.actions.handlers.state_manager`, and `app.services.activity_logger.publish_event`.

## Key env vars

| Variable | Purpose |
|----------|---------|
| `GUNDI_API_BASE_URL` | Gundi platform API endpoint |
| `KEYCLOAK_CLIENT_SECRET` | Auth secret (required for local dev against stage) |
| `INTEGRATION_TYPE_SLUG` | Unique identifier for this integration type |
| `INTEGRATION_SERVICE_URL` | Public URL of this service |
| `REGISTER_ON_START` | `true` to auto-register on startup |
| `REDIS_HOST` / `REDIS_PORT` | Config cache and state store |
| `INTEGRATION_EVENTS_TOPIC` | GCP PubSub topic for activity/error events |
| `PROCESS_WEBHOOKS_IN_BACKGROUND` | Default `true`; processes webhooks async |
| `DIAGNOSTIC_URL_ALLOWLIST` | Comma-separated hostnames allowed for diagnostic forwarding |

Local dev: copy `local/.env.local.example` → `local/.env.local` and set `KEYCLOAK_CLIENT_SECRET` from the stage environment.
