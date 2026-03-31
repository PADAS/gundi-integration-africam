import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.earthranger import get_events, patch_event


def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f


ER_API_URL = "https://test-er.pamdas.org"
ER_TOKEN = "test-token"

WILDLIFE_SIGHTING_ID = "uuid-wildlife-sighting"
ELEPHANT_SIGHTING_ID = "uuid-elephant-sighting"

MOCK_EVENT = {
    "id": "er-event-aaa",
    "event_type": "wildlife_sighting",
    "title": "White rhino sighting",
    "location": {"latitude": -1.4061, "longitude": 35.1425},
    "event_details": {"species": "white rhino", "count": 3},
}


async def _async_gen(items):
    for item in items:
        yield item


@pytest.fixture
def mock_er_client():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    client.get_event_type = AsyncMock(
        side_effect=lambda slug, **kw: {"id": WILDLIFE_SIGHTING_ID, "value": slug}
    )
    client.get_events = MagicMock(return_value=_async_gen([MOCK_EVENT]))
    client.patch_event = AsyncMock(return_value={**MOCK_EVENT, "event_details": {"africam_event_id": "ac-001"}})
    return client


@pytest.mark.asyncio
async def test_get_events_resolves_slugs_to_ids(mock_er_client):
    with patch("app.services.earthranger._make_client", return_value=mock_er_client):
        events = await get_events(
            api_url=ER_API_URL,
            token=ER_TOKEN,
            updated_since=datetime(2024, 1, 1, tzinfo=timezone.utc),
            event_types=["wildlife_sighting"],
        )

    mock_er_client.get_event_type.assert_called_once_with("wildlife_sighting", version="v2.0")

    call_kwargs = mock_er_client.get_events.call_args.kwargs
    assert call_kwargs["event_type"] == WILDLIFE_SIGHTING_ID
    assert events == [MOCK_EVENT]


@pytest.mark.asyncio
async def test_get_events_resolves_multiple_slugs(mock_er_client):
    mock_er_client.get_event_type = AsyncMock(
        side_effect=lambda slug, **kw: {"id": WILDLIFE_SIGHTING_ID if slug == "wildlife_sighting" else ELEPHANT_SIGHTING_ID, "value": slug}
    )
    mock_er_client.get_events = MagicMock(return_value=_async_gen([]))

    with patch("app.services.earthranger._make_client", return_value=mock_er_client):
        await get_events(
            api_url=ER_API_URL,
            token=ER_TOKEN,
            updated_since=datetime(2024, 1, 1, tzinfo=timezone.utc),
            event_types=["wildlife_sighting", "elephant_sighting"],
        )

    assert mock_er_client.get_event_type.call_count == 2
    call_kwargs = mock_er_client.get_events.call_args.kwargs
    assert WILDLIFE_SIGHTING_ID in call_kwargs["event_type"]
    assert ELEPHANT_SIGHTING_ID in call_kwargs["event_type"]


@pytest.mark.asyncio
async def test_get_events_without_event_types_skips_resolution(mock_er_client):
    mock_er_client.get_events = MagicMock(return_value=_async_gen([]))

    with patch("app.services.earthranger._make_client", return_value=mock_er_client):
        await get_events(
            api_url=ER_API_URL,
            token=ER_TOKEN,
            updated_since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    mock_er_client.get_event_type.assert_not_called()
    call_kwargs = mock_er_client.get_events.call_args.kwargs
    assert "event_type" not in call_kwargs


@pytest.mark.asyncio
async def test_patch_event_delegates_to_client(mock_er_client):
    patch_data = {"event_details": {"africam_event_id": "ac-001"}}

    with patch("app.services.earthranger._make_client", return_value=mock_er_client):
        result = await patch_event(ER_API_URL, ER_TOKEN, "er-event-aaa", patch_data)

    mock_er_client.patch_event.assert_called_once_with("er-event-aaa", patch_data)
    assert result["event_details"]["africam_event_id"] == "ac-001"
