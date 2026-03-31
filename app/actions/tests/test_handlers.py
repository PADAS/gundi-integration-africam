import asyncio
import pydantic
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from gundi_core.schemas.v2 import Integration

from app.actions.configurations import AfricamActionConfiguration
from app.actions.handlers import action_process_new_events


def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INTEGRATION_ID = "779ff3ab-5589-4f4c-9e0a-ae8d6c9edff0"

ER_API_URL = "https://test-er-site.pamdas.org"
ER_TOKEN = "er-test-token"
AFRICAM_API_URL = "https://ranger-media.africam.com"
AFRICAM_TOKEN = "africam-test-token"


@pytest.fixture
def africam_config():
    return AfricamActionConfiguration(
        africam_api_url=AFRICAM_API_URL,
        africam_token=AFRICAM_TOKEN,
        event_types=["wildlife_sighting"],
        lookback_hours=1,
    )


@pytest.fixture
def mock_get_er_credentials(mocker):
    return mocker.patch(
        "app.actions.handlers.get_er_credentials_from_destinations",
        new=AsyncMock(return_value=[(ER_API_URL, ER_TOKEN)]),
    )


@pytest.fixture
def mock_integration():
    integration = MagicMock()
    integration.id = INTEGRATION_ID
    return integration


@pytest.fixture
def er_events():
    return [
        {
            "id": "er-event-aaa",
            "event_type": "wildlife_sighting",
            "title": "White rhino sighting",
            "location": {"latitude": -1.4061, "longitude": 35.1425},
            "event_details": {"species": "white rhino", "count": 3},
        },
        {
            "id": "er-event-bbb",
            "event_type": "wildlife_sighting",
            "title": "Elephant sighting",
            "location": {"latitude": -1.500, "longitude": 35.200},
            "event_details": {"species": "elephant", "count": 5},
        },
    ]


@pytest.fixture
def er_events_mixed(er_events):
    """ER event list that includes an event type NOT in the configured filter."""
    return er_events + [
        {
            "id": "er-event-ccc",
            "event_type": "fence_breach",
            "title": "Fence breach at north boundary",
            "location": {"latitude": -1.600, "longitude": 35.300},
            "event_details": {},
        }
    ]


@pytest.fixture
def africam_response():
    return {"status": "updated", "eventId": "e0577b3a-0542-4af4-b1df-b23a9f1583ea"}


@pytest.fixture
def mock_state_manager(mocker):
    manager = mocker.MagicMock()
    manager.get_state = AsyncMock(return_value={})
    manager.set_state = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_state_manager_with_last_execution(mocker):
    last_run = "2024-06-01T12:00:00+00:00"
    manager = mocker.MagicMock()
    manager.get_state = AsyncMock(return_value={"last_execution": last_run})
    manager.set_state = AsyncMock(return_value=None)
    return manager, last_run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pull_events_forwards_matching_events(
    mocker, mock_integration, africam_config, er_events, africam_response,
    mock_state_manager, mock_get_er_credentials
):
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mock_get_events = mocker.patch(
        "app.actions.handlers.get_events", new=AsyncMock(return_value=er_events)
    )
    mock_post = mocker.patch(
        "app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response)
    )
    mock_patch = mocker.patch(
        "app.actions.handlers.patch_event", new=AsyncMock(return_value={})
    )
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    assert result["events_fetched"] == 2
    assert result["events_forwarded"] == 2
    assert result["errors"] == 0

    assert mock_post.call_count == 2
    assert mock_patch.call_count == 2

    # Verify the payload sent to AfricAm for the first event
    first_call = mock_post.call_args_list[0]
    assert first_call.kwargs["api_url"] == AFRICAM_API_URL
    assert first_call.kwargs["event_data"]["id"] == "er-event-aaa"
    assert first_call.kwargs["event_data"]["event_type"] == "wildlife_sighting"

    # Verify the ER patch stores a URL (not the bare ID) merged with existing details
    first_patch = mock_patch.call_args_list[0]
    assert first_patch.kwargs["event_id"] == "er-event-aaa"
    patched_details = first_patch.kwargs["patch_data"]["event_details"]
    assert patched_details["africam_event_url"] == (
        "https://ranger-media.africam.com/gallery/e0577b3a-0542-4af4-b1df-b23a9f1583ea"
    )
    assert patched_details["species"] == "white rhino"


@pytest.mark.asyncio
async def test_pull_events_skips_non_matching_event_types(
    mocker, mock_integration, africam_config, er_events_mixed, africam_response,
    mock_state_manager, mock_get_er_credentials
):
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mocker.patch("app.actions.handlers.get_events", new=AsyncMock(return_value=er_events_mixed))
    mock_post = mocker.patch(
        "app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response)
    )
    mocker.patch("app.actions.handlers.patch_event", new=AsyncMock(return_value={}))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    # 3 fetched, only 2 match wildlife_sighting
    assert result["events_fetched"] == 3
    assert result["events_forwarded"] == 2
    assert result["errors"] == 0
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_pull_events_continues_after_africam_error(
    mocker, mock_integration, africam_config, er_events, mock_state_manager, mock_get_er_credentials
):
    """A failure on one event should not abort the rest of the batch."""
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mocker.patch("app.actions.handlers.get_events", new=AsyncMock(return_value=er_events))

    call_count = 0

    async def flaky_post(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("AfricAm is down")
        return {"status": "updated", "eventId": "africam-002"}

    mocker.patch("app.actions.handlers.post_event_to_africam", new=flaky_post)
    mock_patch = mocker.patch(
        "app.actions.handlers.patch_event", new=AsyncMock(return_value={})
    )
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    assert result["events_fetched"] == 2
    assert result["events_forwarded"] == 1
    assert result["errors"] == 1
    assert mock_patch.call_count == 1


@pytest.mark.asyncio
async def test_pull_events_uses_state_for_updated_since(
    mocker, mock_integration, africam_config, africam_response, mock_state_manager, mock_get_er_credentials
):
    """When state has a last_execution, it should be used as the updated_since window."""
    last_run = "2024-06-01T12:00:00+00:00"
    mock_state_manager.get_state = AsyncMock(return_value={"last_execution": last_run})
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)

    mock_get_events = mocker.patch(
        "app.actions.handlers.get_events", new=AsyncMock(return_value=[])
    )
    mocker.patch("app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response))
    mocker.patch("app.actions.handlers.patch_event", new=AsyncMock(return_value={}))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    await action_process_new_events(integration=mock_integration, action_config=africam_config)

    call_kwargs = mock_get_events.call_args.kwargs
    assert call_kwargs["updated_since"] == datetime.fromisoformat(last_run)


@pytest.mark.asyncio
async def test_pull_events_processes_multiple_destinations(
    mocker, mock_integration, africam_config, africam_response, mock_state_manager
):
    """All destinations in the connection should be processed independently."""
    ER_API_URL_2 = "https://test-er-site-2.pamdas.org"
    ER_TOKEN_2 = "er-test-token-2"
    mocker.patch(
        "app.actions.handlers.get_er_credentials_from_destinations",
        new=AsyncMock(return_value=[(ER_API_URL, ER_TOKEN), (ER_API_URL_2, ER_TOKEN_2)]),
    )
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mock_get_events = mocker.patch(
        "app.actions.handlers.get_events", new=AsyncMock(return_value=[
            {
                "id": "er-event-aaa",
                "event_type": "wildlife_sighting",
                "title": "Rhino",
                "location": {"latitude": -1.4, "longitude": 35.1},
                "event_details": {},
            }
        ])
    )
    mock_post = mocker.patch(
        "app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response)
    )
    mocker.patch("app.actions.handlers.patch_event", new=AsyncMock(return_value={}))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    # get_events called once per destination
    assert mock_get_events.call_count == 2
    # one event from each destination forwarded
    assert result["events_fetched"] == 2
    assert result["events_forwarded"] == 2
    assert result["errors"] == 0
    # state saved once per destination
    assert mock_state_manager.set_state.call_count == 2
    calls = {c.kwargs["source_id"] for c in mock_state_manager.set_state.call_args_list}
    assert calls == {ER_API_URL, ER_API_URL_2}


@pytest.mark.asyncio
async def test_pull_events_saves_state_after_run(
    mocker, mock_integration, africam_config, er_events, africam_response,
    mock_state_manager, mock_get_er_credentials
):
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mocker.patch("app.actions.handlers.get_events", new=AsyncMock(return_value=er_events))
    mocker.patch("app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response))
    mocker.patch("app.actions.handlers.patch_event", new=AsyncMock(return_value={}))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    await action_process_new_events(integration=mock_integration, action_config=africam_config)

    mock_state_manager.set_state.assert_called_once()
    call_kwargs = mock_state_manager.set_state.call_args.kwargs
    assert call_kwargs["integration_id"] == INTEGRATION_ID
    assert call_kwargs["action_id"] == "process_new_events"
    assert call_kwargs["source_id"] == ER_API_URL
    assert "last_execution" in call_kwargs["state"]


@pytest.mark.asyncio
async def test_pull_events_no_id_in_africam_response_skips_patch(
    mocker, mock_integration, africam_config, er_events, mock_state_manager, mock_get_er_credentials
):
    """If AfricAm returns no event ID, we should still count the event as forwarded but skip the patch."""
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mocker.patch("app.actions.handlers.get_events", new=AsyncMock(return_value=er_events[:1]))
    mocker.patch(
        "app.actions.handlers.post_event_to_africam",
        new=AsyncMock(return_value={"status": "ok"}),  # no eventId
    )
    mock_patch = mocker.patch("app.actions.handlers.patch_event", new=AsyncMock(return_value={}))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    assert result["events_forwarded"] == 1
    assert result["errors"] == 0
    mock_patch.assert_not_called()


@pytest.mark.asyncio
async def test_pull_events_uses_er_credentials_from_destination(
    mocker, mock_integration, africam_config, er_events, africam_response,
    mock_state_manager, mock_get_er_credentials
):
    """ER URL and token are read from the connection destination, not from the action config."""
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mock_get_events = mocker.patch(
        "app.actions.handlers.get_events", new=AsyncMock(return_value=er_events)
    )
    mock_patch = mocker.patch(
        "app.actions.handlers.patch_event", new=AsyncMock(return_value={})
    )
    mocker.patch("app.actions.handlers.post_event_to_africam", new=AsyncMock(return_value=africam_response))
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    await action_process_new_events(integration=mock_integration, action_config=africam_config)

    mock_get_er_credentials.assert_called_once_with(INTEGRATION_ID)

    get_events_kwargs = mock_get_events.call_args.kwargs
    assert get_events_kwargs["api_url"] == ER_API_URL
    assert get_events_kwargs["token"] == ER_TOKEN

    patch_kwargs = mock_patch.call_args.kwargs
    assert patch_kwargs["api_url"] == ER_API_URL
    assert patch_kwargs["token"] == ER_TOKEN


# ---------------------------------------------------------------------------
# AfricamActionConfiguration validator tests
# ---------------------------------------------------------------------------

BASE_CONFIG = dict(
    africam_api_url="https://ranger-media.africam.com",
    africam_token="token",
    event_types=["wildlife_sighting"],
)


@pytest.mark.asyncio
async def test_pull_events_skips_already_processed_events(
    mocker, mock_integration, africam_config, mock_state_manager, mock_get_er_credentials
):
    """Events that already have africam_event_url in their details should be skipped."""
    already_processed = {
        "id": "er-event-already",
        "event_type": "wildlife_sighting",
        "title": "Already sent",
        "location": {"latitude": -1.0, "longitude": 35.0},
        "event_details": {"africam_event_url": "https://ranger-media.africam.com/gallery/existing-id"},
    }
    mocker.patch("app.actions.handlers.state_manager", mock_state_manager)
    mocker.patch("app.actions.handlers.get_events", new=AsyncMock(return_value=[already_processed]))
    mock_post = mocker.patch("app.actions.handlers.post_event_to_africam", new=AsyncMock())
    mocker.patch("app.services.activity_logger.publish_event", new=AsyncMock())

    result = await action_process_new_events(integration=mock_integration, action_config=africam_config)

    assert result["events_fetched"] == 1
    assert result["events_forwarded"] == 0
    mock_post.assert_not_called()


def test_url_template_default_is_valid():
    config = AfricamActionConfiguration(**BASE_CONFIG)
    url = config.africam_event_url_template.format(africam_event_id="abc-123")
    assert url == "https://ranger-media.africam.com/gallery/abc-123"


def test_url_template_custom_valid():
    config = AfricamActionConfiguration(
        **BASE_CONFIG,
        africam_event_url_template="https://example.com/events/{africam_event_id}/view",
    )
    assert config.africam_event_url_template.format(africam_event_id="x") == (
        "https://example.com/events/x/view"
    )


def test_url_template_missing_placeholder_raises():
    with pytest.raises(pydantic.ValidationError, match="africam_event_id"):
        AfricamActionConfiguration(
            **BASE_CONFIG,
            africam_event_url_template="https://example.com/events/no-placeholder",
        )


def test_url_template_unknown_placeholder_raises():
    with pytest.raises(pydantic.ValidationError, match="Invalid format string"):
        AfricamActionConfiguration(
            **BASE_CONFIG,
            africam_event_url_template="https://example.com/{africam_event_id}/{unknown}",
        )


def test_url_template_non_https_raises():
    with pytest.raises(pydantic.ValidationError):
        AfricamActionConfiguration(
            **BASE_CONFIG,
            africam_event_url_template="http://example.com/{africam_event_id}",
        )


def test_url_template_pattern_in_schema():
    schema = AfricamActionConfiguration.schema()
    pattern = schema["properties"]["africam_event_url_template"]["pattern"]
    assert "africam_event_id" in pattern
    assert pattern.startswith("^https://")
