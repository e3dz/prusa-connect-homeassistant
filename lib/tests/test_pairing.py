"""App pairing: the RFC 8628 device authorization grant against the fake server."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest

from prusa_connect import (
    SCOPE_READ,
    ApiError,
    AppPairing,
    PairingDeniedError,
    PairingExpiredError,
    PrusaConnect,
)

from .conftest import FakeServer

Make = Callable[..., PrusaConnect]
PENDING = "core.auth/APP_PAIRING_PENDING"
SLOW_DOWN = "core.auth/APP_PAIRING_SLOW_DOWN"


async def test_request_app_pairing(make_client: Make, fake: FakeServer) -> None:
    pairing = await make_client(token=None).request_app_pairing("Home Assistant " + "x" * 80)
    assert pairing.user_code == "BCDF-GHJK"
    assert pairing.device_code == "secret-device-code"
    assert pairing.verification_uri_complete.endswith("/pair?code=BCDF-GHJK")
    assert (pairing.expires_in, pairing.interval) == (600, 5)
    assert fake.pairing_requests == [{"app_name": ("Home Assistant " + "x" * 80)[:64], "scopes": ["operate"]}]


async def test_request_app_pairing_with_scopes(make_client: Make, fake: FakeServer) -> None:
    await make_client(token=None).request_app_pairing("app", [SCOPE_READ])
    assert fake.pairing_requests[0]["scopes"] == ["read"]


def test_pairing_defaults() -> None:
    pairing = AppPairing.from_dict(
        {"device_code": "d", "user_code": "u", "verification_uri": "http://h/pair"}
    )
    assert pairing.verification_uri_complete == "http://h/pair"
    assert (pairing.expires_in, pairing.interval) == (600, 5)


async def test_wait_polls_until_approved(make_client: Make, fake: FakeServer) -> None:
    fake.pairing_answers = [PENDING, SLOW_DOWN, PENDING, "pcl_paired"]
    client = make_client(token=None)
    pairing = await client.request_app_pairing("app")
    with patch("prusa_connect.client.asyncio.sleep", new=AsyncMock()) as sleep:
        assert await client.wait_for_app_pairing(pairing) == "pcl_paired"
    # slow_down adds five seconds to every later wait (RFC 8628 section 3.5).
    assert [call.args[0] for call in sleep.await_args_list] == [5, 5, 10, 10]
    assert fake.pairing_polls == [{"device_code": "secret-device-code"}] * 4


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        ("core.auth/APP_PAIRING_DENIED", PairingDeniedError),
        ("core.auth/APP_PAIRING_EXPIRED", PairingExpiredError),
        ("core.auth/APP_PAIRING_UNKNOWN", PairingExpiredError),
        ("core.auth/SOMETHING_ELSE", ApiError),
    ],
)
async def test_wait_ends_without_a_token(
    make_client: Make, fake: FakeServer, answer: str, error: type[Exception]
) -> None:
    fake.pairing_answers = [PENDING, answer]
    client = make_client(token=None)
    pairing = await client.request_app_pairing("app")
    with patch("prusa_connect.client.asyncio.sleep", new=AsyncMock()), pytest.raises(error):
        await client.wait_for_app_pairing(pairing)


async def test_wait_gives_up_after_expiry(make_client: Make, fake: FakeServer) -> None:
    fake.pairing_answers = [PENDING]
    client = make_client(token=None)
    pairing = AppPairing("secret-device-code", "BCDF-GHJK", "u", "u", expires_in=0, interval=0)
    with patch("prusa_connect.client.asyncio.sleep", new=AsyncMock()), pytest.raises(PairingExpiredError):
        await client.wait_for_app_pairing(pairing)
    assert fake.pairing_polls == []
