from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import stamina

from app.services.gundi import get_er_credentials_from_destinations


@pytest.fixture
def stamina_testing():
    stamina.set_testing(True, attempts=2)
    yield
    stamina.set_testing(False)


@pytest.fixture
def no_blocking_sleep(mocker):
    """Fail the test if a retry back-off runs time.sleep inside the event loop."""
    return mocker.patch(
        "time.sleep", side_effect=AssertionError("blocking time.sleep called inside a coroutine")
    )


def _destination(dest_id, base_url):
    d = MagicMock()
    d.id = dest_id
    d.base_url = base_url
    return d


def _integration_with_token(token):
    auth = MagicMock()
    auth.data = {"token": token}
    integration = MagicMock()
    integration.get_action_config = MagicMock(return_value=auth)
    return integration


@pytest.fixture
def mock_gundi_client(mocker):
    client = MagicMock()
    connection = MagicMock()
    connection.destinations = [_destination("dest-1", "https://er.example.org")]
    client.get_connection_details = AsyncMock(return_value=connection)
    client.get_integration_details = AsyncMock(return_value=_integration_with_token("er-token"))
    cls = mocker.patch("app.services.gundi.GundiClient")
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_credentials_lookup_retries_without_blocking_the_event_loop(
    mock_gundi_client, stamina_testing, no_blocking_sleep
):
    connection = await mock_gundi_client.get_connection_details()
    mock_gundi_client.get_connection_details.side_effect = [
        httpx.ConnectError("boom"),
        connection,
    ]

    result = await get_er_credentials_from_destinations("integration-1")

    assert result == [("https://er.example.org", "er-token")]
    assert mock_gundi_client.get_connection_details.await_count == 3  # fixture probe + 2 attempts
