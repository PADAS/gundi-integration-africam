import logging
from datetime import datetime
from typing import List, Optional

from erclient import AsyncERClient

logger = logging.getLogger(__name__)


def _make_client(api_url: str, token: str) -> AsyncERClient:
    return AsyncERClient(service_root=api_url, token=token)


async def _resolve_event_type_ids(client: AsyncERClient, slugs: List[str]) -> List[str]:
    """Resolve event-type natural keys (e.g. 'wildlife_sighting') to their UUIDs."""
    ids = []
    for slug in slugs:
        event_type = await client.get_event_type(slug, version="v2.0")
        ids.append(event_type["id"])
    return ids


async def get_events(
    api_url: str,
    token: str,
    updated_since: datetime,
    event_types: Optional[List[str]] = None,
) -> List[dict]:
    """Fetch all events from EarthRanger updated since the given datetime.

    ``event_types`` is a list of natural-key slugs (e.g. ``['wildlife_sighting']``).
    They are resolved to UUIDs before querying, as the EarthRanger API requires IDs.
    """
    events = []
    async with _make_client(api_url, token) as client:
        params = {"updated_since": updated_since.isoformat()}
        if event_types:
            ids = await _resolve_event_type_ids(client, event_types)
            params["event_type"] = ",".join(ids)

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
