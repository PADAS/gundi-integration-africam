import logging
from datetime import datetime, timezone, timedelta

from gundi_core.events import LogLevel

from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger, log_action_activity
from app.services.africam import post_event as post_event_to_africam
from app.services.earthranger import get_events, patch_event
from app.services.gundi import get_er_credentials_from_destination
from app.services.state import IntegrationStateManager
from .configurations import AfricamActionConfiguration

logger = logging.getLogger(__name__)
state_manager = IntegrationStateManager()


@crontab_schedule("* * * * *")
@activity_logger()
async def action_process_new_events(integration, action_config: AfricamActionConfiguration):
    '''
    Read new events from EarthRanger and forward them to Africam.
    Annotate the EarthRanger event with the Africam event URL.
    '''
    integration_id = str(integration.id)
    er_base_url, er_token = await get_er_credentials_from_destination(integration_id)
    africam_token = action_config.africam_token.get_secret_value()

    # Determine the start of the fetch window from state, falling back to lookback_hours
    state = await state_manager.get_state(integration_id, "pull_events")
    if last_execution := state.get("last_execution"):
        updated_since = datetime.fromisoformat(last_execution)
    else:
        updated_since = datetime.now(timezone.utc) - timedelta(hours=action_config.lookback_hours)

    now = datetime.now(timezone.utc)

    await log_action_activity(
        integration_id=integration_id,
        action_id="process_new_events",
        title=f"Fetching EarthRanger events updated since {updated_since.isoformat()}",
        level=LogLevel.INFO,
        data={
            "updated_since": updated_since.isoformat(),
            "event_types": action_config.event_types,
        },
    )

    events = await get_events(
        api_url=er_base_url,
        token=er_token,
        updated_since=updated_since,
        event_types=action_config.event_types,
    )
    logger.info(f"Fetched {len(events)} event(s) from EarthRanger for integration {integration_id}")

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
                merged_details = {**(event.get("event_details") or {}), "africam_event_url": africam_event_url}
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

    # Persist the fetch timestamp so the next run is incremental
    await state_manager.set_state(
        integration_id=integration_id,
        action_id="process_new_events",
        state={"last_execution": now.isoformat()},
    )

    result = {"events_fetched": len(events), "events_forwarded": forwarded, "errors": errors}
    await log_action_activity(
        integration_id=integration_id,
        action_id="process_new_events",
        title=f"Forwarded {forwarded} event(s) to Africam ({errors} error(s))",
        level=LogLevel.WARNING if errors else LogLevel.INFO,
        data=result,
    )
    return result
