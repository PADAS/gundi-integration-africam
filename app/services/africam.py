import logging

import httpx
import stamina

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def post_event(api_url: str, token: str, event_data: dict) -> dict:
    """POST an EarthRanger event to the Africam webhook endpoint.

    Expected payload shape (from Africam API docs):
        {
            "event_type": "event_update",
            "data": {
                "id": "<er-event-id>",
                "event_type": "<er-event-type>",
                "title": "...",
                "location": {"latitude": ..., "longitude": ...},
                "event_details": {...}
            }
        }

    Returns the parsed JSON response from Africam, e.g.::

        {"status": "updated", "eventId": "e0577b3a-0542-4af4-b1df-b23a9f1583ea"}
    """
    url = f"{api_url.rstrip('/')}/events/webhook"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "event_type": "event_update",
        "data": event_data,
    }

    response = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in stamina.retry_context(
            on=httpx.HTTPError, wait_initial=5.0, wait_jitter=5.0, wait_max=60.0
        ):
            with attempt:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

    logger.debug(f"Posted event {event_data.get('id')} to Africam ({url})")
    return response.json()
