import logging
from datetime import datetime, timezone, timedelta

from gundi_core.events import LogLevel

from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger, log_action_activity
from app.services.africam import post_event as post_event_to_africam
from app.services.earthranger import get_events, patch_event, resolve_event_type_ids
from app.services.gundi import get_er_credentials_from_destinations
from app.services.state import IntegrationStateManager
from .configurations import AfricamActionConfiguration

logger = logging.getLogger(__name__)
state_manager = IntegrationStateManager()

# Missing event types are re-checked every minute, but we only surface the warning
# in the Activity Log at most once per destination within this interval to avoid noise.
MISSING_EVENT_TYPE_WARNING_INTERVAL = timedelta(hours=1)


@crontab_schedule("* * * * *")
@activity_logger()
async def action_process_new_events(integration, action_config: AfricamActionConfiguration):
    '''
    Read new events from EarthRanger and forward them to Africam.
    Annotate the EarthRanger event with the Africam event URL.
    Processes all EarthRanger destinations configured on the connection.
    '''
    integration_id = str(integration.id)
    er_destinations = await get_er_credentials_from_destinations(integration_id)
    africam_token = action_config.africam_token.get_secret_value()

    total_fetched = 0
    total_forwarded = 0
    total_errors = 0

    for er_base_url, er_token in er_destinations:
        # Use er_base_url as source_id so each destination has independent state
        state = await state_manager.get_state(
            integration_id, "process_new_events", source_id=er_base_url
        )
        now = datetime.now(timezone.utc)
        # Never look back further than lookback_hours, even if a saved watermark
        # is stale (e.g. after a long outage or misconfiguration).
        lookback_floor = now - timedelta(hours=action_config.lookback_hours)

        # Resolve configured event-type slugs to IDs. Slugs that don't exist on this
        # ER site (404) are reported as missing rather than aborting the run.
        resolved, missing_slugs = await resolve_event_type_ids(
            api_url=er_base_url,
            token=er_token,
            slugs=action_config.event_types,
        )

        if missing_slugs:
            last_warned = state.get("last_missing_warning")
            warning_due = (
                last_warned is None
                or now - datetime.fromisoformat(last_warned) >= MISSING_EVENT_TYPE_WARNING_INTERVAL
            )
            if warning_due:
                await log_action_activity(
                    integration_id=integration_id,
                    action_id="process_new_events",
                    title=(
                        f"Configured event type(s) not found on {er_base_url}, skipping: "
                        f"{', '.join(missing_slugs)}"
                    ),
                    level=LogLevel.WARNING,
                    data={"er_base_url": er_base_url, "missing_event_types": missing_slugs},
                )
                # Record when we warned so we throttle repeat warnings for this destination.
                state = {**state, "last_missing_warning": now.isoformat()}

        if action_config.event_types and not resolved:
            # None of the configured event types exist on this site; skip fetching
            # entirely so we don't pull every event. Persist state (to keep the throttle
            # timestamp) but leave the watermarks unchanged so the window (up to
            # lookback_hours) is retried once the configuration is corrected.
            logger.warning(
                f"No configured event types resolved on {er_base_url}; skipping fetch"
            )
            await state_manager.set_state(
                integration_id=integration_id,
                action_id="process_new_events",
                source_id=er_base_url,
                state=state,
            )
            continue

        # Each event type carries its own watermark, so a type that was missing
        # (or newly configured) is fetched from where *it* left off rather than from
        # the newest type's watermark. State written before this existed holds a
        # single last_execution; seed every resolved type from it once so the upgrade
        # doesn't re-fetch a full lookback window.
        watermarks = state.get("last_execution_by_type")
        if watermarks is None:
            legacy = state.get("last_execution")
            watermarks = {slug: legacy for slug in resolved} if legacy else {}

        # Operator reset: while force_run_since_start is on, every resolved type is
        # fetched from start_datetime, ignoring its watermark and the lookback cap.
        # The run still advances the watermarks below, so turning the toggle off
        # afterwards resumes incremental fetching from this run's start time.
        forced_since = None
        if action_config.force_run_since_start and action_config.start_datetime is not None:
            forced_since = action_config.start_datetime
            if forced_since.tzinfo is None:
                forced_since = forced_since.replace(tzinfo=timezone.utc)
            await log_action_activity(
                integration_id=integration_id,
                action_id="process_new_events",
                title=(
                    f"Force Run From Start Datetime is on: fetching every event type on "
                    f"{er_base_url} from {forced_since.isoformat()}; turn it off once the "
                    f"catch-up run completes"
                ),
                level=LogLevel.WARNING,
                data={"er_base_url": er_base_url, "start_datetime": forced_since.isoformat()},
            )

        windows = {}  # updated_since -> [slug, ...]; types sharing a watermark share a fetch
        capped = {}   # slug -> stale watermark, for the operator warning
        for slug in resolved:
            if forced_since is not None:
                windows.setdefault(forced_since, []).append(slug)
                continue
            watermark_dt = None
            if watermark := watermarks.get(slug):
                watermark_dt = datetime.fromisoformat(watermark)
                if watermark_dt.tzinfo is None:
                    # Hand-seeded or migrated state may lack a zone; we always write UTC.
                    watermark_dt = watermark_dt.replace(tzinfo=timezone.utc)
            if watermark_dt is not None and watermark_dt < lookback_floor:
                capped[slug] = watermark
                watermark_dt = None
            updated_since = watermark_dt or lookback_floor
            windows.setdefault(updated_since, []).append(slug)

        if capped:
            # Events updated between the stale watermark and the floor are skipped for
            # good. Surface that so an operator can backfill by touching events if needed.
            # This fires once per gap: the run below writes fresh watermarks.
            await log_action_activity(
                integration_id=integration_id,
                action_id="process_new_events",
                title=(
                    f"Fetch window on {er_base_url} capped at {action_config.lookback_hours}h "
                    f"for {', '.join(capped)}; events updated before "
                    f"{lookback_floor.isoformat()} were skipped"
                ),
                level=LogLevel.WARNING,
                data={
                    "er_base_url": er_base_url,
                    "capped_event_types": capped,
                    "capped_to": lookback_floor.isoformat(),
                    "lookback_hours": action_config.lookback_hours,
                },
            )

        events = []
        for updated_since, slugs in windows.items():
            await log_action_activity(
                integration_id=integration_id,
                action_id="process_new_events",
                title=(
                    f"Fetching EarthRanger events from {er_base_url} updated since "
                    f"{updated_since.isoformat()} for {', '.join(slugs)}"
                ),
                level=LogLevel.INFO,
                data={
                    "er_base_url": er_base_url,
                    "updated_since": updated_since.isoformat(),
                    "event_types": slugs,
                },
            )
            events += await get_events(
                api_url=er_base_url,
                token=er_token,
                updated_since=updated_since,
                event_type_ids=[resolved[slug] for slug in slugs],
            )
        logger.info(
            f"Fetched {len(events)} event(s) from {er_base_url} for integration {integration_id}"
        )

        forwarded = 0
        errors = 0

        for event in events:
            er_event_id = event.get("id")
            event_type = event.get("event_type", "")

            if event_type not in action_config.event_types:
                continue

            if (event.get("event_details") or {}).get("africam_event_url"):
                logger.debug(f"Skipping ER event {er_event_id}: africam_event_url already set")
                continue

            event_data = {
                "id": er_event_id,
                "event_type": event_type,
                "title": event.get("title", ""),
                "location": event.get("location"),
                "event_details": event.get("event_details") or {},
            }

            try:
                africam_response = await post_event_to_africam(
                    api_url=action_config.africam_api_url,
                    token=africam_token,
                    event_data=event_data,
                )
                africam_event_id = africam_response.get("eventId")

                if africam_event_id:
                    africam_event_url = action_config.africam_event_url_template.format(
                        africam_event_id=africam_event_id
                    )
                    merged_details = {
                        **(event.get("event_details") or {}),
                        "africam_event_url": africam_event_url,
                    }
                    await patch_event(
                        api_url=er_base_url,
                        token=er_token,
                        event_id=er_event_id,
                        patch_data={"event_details": merged_details},
                    )
                else:
                    logger.warning(
                        f"Africam response for ER event {er_event_id} contained no event ID: {africam_response}"
                    )

                forwarded += 1
            except Exception as e:
                logger.exception(f"Error processing ER event {er_event_id}: {e}")
                errors += 1

        # Advance the watermark of every type we just fetched; a missing type keeps
        # its old one. Merge onto existing state so the missing-event-type warning
        # throttle survives. last_execution is still written so a rollback to the
        # single-watermark release keeps working.
        await state_manager.set_state(
            integration_id=integration_id,
            action_id="process_new_events",
            source_id=er_base_url,
            state={
                **state,
                "last_execution": now.isoformat(),
                "last_execution_by_type": {
                    **watermarks,
                    **{slug: now.isoformat() for slug in resolved},
                },
            },
        )

        total_fetched += len(events)
        total_forwarded += forwarded
        total_errors += errors

    result = {
        "events_fetched": total_fetched,
        "events_forwarded": total_forwarded,
        "errors": total_errors,
    }
    await log_action_activity(
        integration_id=integration_id,
        action_id="process_new_events",
        title=f"Forwarded {total_forwarded} event(s) to Africam ({total_errors} error(s))",
        level=LogLevel.WARNING if total_errors else LogLevel.INFO,
        data=result,
    )
    return result
