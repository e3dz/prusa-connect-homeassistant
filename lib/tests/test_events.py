"""The event stream: parsing, reconnecting and resuming."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from prusa_connect import (
    AuthenticationError,
    Event,
    ForbiddenError,
    PrusaConnect,
    StreamConnected,
    StreamDisconnected,
)
from prusa_connect.sse import SSEParser

from .conftest import FIXTURES, FakeServer

Make = Callable[..., PrusaConnect]
RECORDED = (FIXTURES / "events.txt").read_text()


def test_parser_dispatches_on_blank_line() -> None:
    parser = SSEParser()
    lines = ["retry: 2000", "", ": comment", "id: 7", "event: e", "data: a", "data:b", ""]
    frames = [f for f in (parser.feed(line) for line in lines) if f is not None]
    assert len(frames) == 1
    assert frames[0].event == "e"
    assert frames[0].data == "a\nb"
    assert frames[0].id == "7"
    assert parser.retry == 2000
    assert parser.last_event_id == "7"


def test_parser_frame_without_id_keeps_last_id() -> None:
    parser = SSEParser("old")
    parser.feed("data: x")
    frame = parser.feed("")
    assert frame is not None
    assert frame.id is None
    assert frame.event == "message"
    assert parser.last_event_id == "old"


async def test_recorded_stream_and_resume(make_client: Make, fake: FakeServer) -> None:
    fake.event_bodies = [RECORDED, RECORDED]
    items: list[object] = []
    async for item in make_client().events(min_backoff=0.01, max_backoff=0.01):
        items.append(item)
        if sum(isinstance(i, StreamConnected) for i in items) == 2:
            break
    assert isinstance(items[0], StreamConnected)
    assert not items[0].reconnect
    events = [i for i in items if isinstance(i, Event)]
    telemetry = [e for e in events if e.type.endswith("telemetry.sampled")]
    assert {e.data["path"] for e in telemetry} >= {"/tools/0/nozzle_temp", "/job/progress"}
    presence = [e for e in events if e.type.endswith("presence.changed")]
    assert presence[0].data["connected"] is False
    assert presence[0].id == "01M5QAX4:device/637d5756-4645-4a08-906f-e8dbb9afc56f:412"
    assert any(isinstance(i, StreamDisconnected) for i in items)
    assert isinstance(items[-1], StreamConnected)
    assert items[-1].reconnect
    # The second request resumes from the last frame that carried an id.
    assert fake.event_requests[1]["Last-Event-ID"] == presence[0].id


async def test_server_error_retries(make_client: Make, fake: FakeServer) -> None:
    fake.event_bodies = [503, RECORDED]
    items: list[object] = []
    async for item in make_client().events(min_backoff=0.01, max_backoff=0.01):
        items.append(item)
        if isinstance(item, StreamConnected):
            break
    assert isinstance(items[0], StreamDisconnected)
    assert items[0].error is not None


async def test_unauthorized_raises(make_client: Make) -> None:
    with pytest.raises(AuthenticationError):
        async for _ in make_client(token="bad").events():
            pass


async def test_forbidden_raises(make_client: Make, fake: FakeServer) -> None:
    fake.event_bodies = [403]
    with pytest.raises(ForbiddenError):
        async for _ in make_client().events():
            pass


async def test_auth_expired_frame_raises(make_client: Make, fake: FakeServer) -> None:
    fake.event_bodies = ['event: prusa-connect.auth.expired\ndata: {"type":"prusa-connect.auth.expired"}\n\n']
    with pytest.raises(AuthenticationError):
        async for _ in make_client().events():
            pass


async def test_non_json_frame_is_skipped(make_client: Make, fake: FakeServer) -> None:
    fake.event_bodies = ["data: not json\n\ndata: [1]\n\n" + RECORDED]
    async for item in make_client().events(types=["a", "b"]):
        if isinstance(item, Event):
            assert item.type.startswith("com.prusa")
            break
