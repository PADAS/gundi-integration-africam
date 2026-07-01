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
        if last_execution := state.get("last_execution"):
            updated_since = datetime.fromisoformat(last_execution)
        else:
            updated_since = datetime.now(timezone.utc) - timedelta(hours=action_config.lookback_hours)

        now = datetime.now(timezone.utc)

        # Resolve configured event-type slugs to IDs. Slugs that don't exist on this
        # ER site (404) are reported as missing rather than aborting the run.
        resolved_ids, missing_slugs = await resolve_event_type_ids(
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

        if action_config.event_types and not resolved_ids:
            # None of the configured event types exist on this site; skip fetching
            # entirely so we don't pull every event. Persist state (to keep the throttle
            # timestamp) but leave last_execution unchanged so the window is retried
            # once the configuration is corrected.
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

        await log_action_activity(
            integration_id=integration_id,
            action_id="process_new_events",
            title=f"Fetching EarthRanger events from {er_base_url} updated since {updated_since.isoformat()}",
            level=LogLevel.INFO,
            data={
                "er_base_url": er_base_url,
                "updated_since": updated_since.isoformat(),
                "event_types": action_config.event_types,
            },
        )

        events = await get_events(
            api_url=er_base_url,
            token=er_token,
            updated_since=updated_since,
            event_type_ids=resolved_ids,
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

        # Persist the fetch timestamp so the next run is incremental for this destination.
        # Merge onto existing state so the missing-event-type warning throttle survives.
        await state_manager.set_state(
            integration_id=integration_id,
            action_id="process_new_events",
            source_id=er_base_url,
            state={**state, "last_execution": now.isoformat()},
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
