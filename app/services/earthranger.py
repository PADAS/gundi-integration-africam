import logging
from datetime import datetime
from typing import List, Optional, Tuple

from erclient import AsyncERClient, ERClientNotFound

logger = logging.getLogger(__name__)


def _make_client(api_url: str, token: str) -> AsyncERClient:
    return AsyncERClient(service_root=api_url, token=token)


async def resolve_event_type_ids(
    api_url: str, token: str, slugs: List[str]
) -> Tuple[List[str], List[str]]:
    """Resolve event-type natural keys (e.g. 'wildlife_sighting') to their UUIDs.

    The EarthRanger API requires event-type IDs, not slugs, when filtering events.
    A slug that doesn't exist on the ER site returns a 404; rather than aborting,
    it is collected into the returned ``missing`` list so the caller can report it.

    Returns a ``(resolved_ids, missing_slugs)`` tuple.
    """
    resolved: List[str] = []
    missing: List[str] = []
    async with _make_client(api_url, token) as client:
        for slug in slugs:
            try:
                event_type = await client.get_event_type(slug, version="v2.0")
            except ERClientNotFound:
                logger.warning(f"Event type '{slug}' not found on {api_url}; skipping")
                missing.append(slug)
                continue
            resolved.append(event_type["id"])
    return resolved, missing


async def get_events(
    api_url: str,
    token: str,
    updated_since: datetime,
    event_type_ids: Optional[List[str]] = None,
) -> List[dict]:
    """Fetch all events from EarthRanger updated since the given datetime.

    ``event_type_ids`` is a list of resolved event-type UUIDs to filter by
    (see :func:`resolve_event_type_ids`). When omitted, no event-type filter is
    applied and all updated events are returned.
    """
    events = []
    async with _make_client(api_url, token) as client:
        params = {"updated_since": updated_since.isoformat()}
        if event_type_ids:
            params["event_type"] = ",".join(event_type_ids)

        async for event in client.get_events(**params):
            events.append(event)

    logger.debug(f"Fetched {len(events)} events from EarthRanger ({api_url})")
    return events


async def patch_event(api_url: str, token: str, event_id: str, patch_data: dict) -> dict:
    """Patch a single EarthRanger event."""
    async with _make_client(api_url, token) as client:
        result = await client.patch_event(event_id, patch_data)
    logger.debug(f"Patched EarthRanger event {event_id}")
    return result
