import httpx
import pytest
import stamina

from app.services.africam import post_event

AFRICAM_API_URL = "https://ranger-media.africam.com"


@pytest.fixture
def stamina_testing():
    # Retry immediately instead of backing off, but keep stamina's retry loop active.
    stamina.set_testing(True, attempts=2)
    yield
    stamina.set_testing(False)


@pytest.fixture
def no_blocking_sleep(mocker):
    """Fail the test if a retry back-off runs time.sleep inside the event loop."""
    return mocker.patch(
        "time.sleep", side_effect=AssertionError("blocking time.sleep called inside a coroutine")
    )


def _client_with_transport(mocker, handler):
    real_client = httpx.AsyncClient
    mocker.patch(
        "app.services.africam.httpx.AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )


@pytest.mark.asyncio
async def test_post_event_retries_a_5xx_without_blocking_the_event_loop(
    mocker, stamina_testing, no_blocking_sleep
):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": "updated", "eventId": "abc"})

    _client_with_transport(mocker, handler)

    result = await post_event(AFRICAM_API_URL, "token", {"id": "er-1"})

    assert result == {"status": "updated", "eventId": "abc"}
    assert len(calls) == 2
    assert calls[0].url == f"{AFRICAM_API_URL}/events/webhook"
    assert calls[0].headers["Authorization"] == "Bearer token"
