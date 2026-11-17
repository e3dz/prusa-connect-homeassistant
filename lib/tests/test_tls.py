"""Certificate fingerprints and pinning against a real TLS listener."""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator

import aiohttp
import pytest
import trustme
from aiohttp import web
from aiohttp.test_utils import TestServer

from prusa_connect import (
    CannotConnectError,
    CertificateError,
    PrusaConnect,
    certificate_fingerprint,
    fetch_certificate_fingerprint,
    normalize_fingerprint,
)


def test_normalize_fingerprint() -> None:
    raw = "ab" * 32
    expected = ":".join(["AB"] * 32)
    assert normalize_fingerprint(raw) == expected
    assert normalize_fingerprint(expected.lower()) == expected
    assert normalize_fingerprint(" ".join(["ab"] * 32)) == expected
    with pytest.raises(ValueError, match="64 hex digits"):
        normalize_fingerprint("abc")


@pytest.fixture(scope="module")
def ca() -> trustme.CA:
    return trustme.CA()


@pytest.fixture
async def tls_server(ca: trustme.CA) -> AsyncIterator[tuple[TestServer, str]]:
    cert = ca.issue_cert("127.0.0.1")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert.configure_cert(context)
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "version": "1"})

    app.router.add_get("/api/v1/health", health)
    server = TestServer(app, host="127.0.0.1", scheme="https")
    await server.start_server(ssl=context)
    fingerprint = certificate_fingerprint(ssl.PEM_cert_to_DER_cert(cert.cert_chain_pems[0].bytes().decode()))
    yield server, fingerprint
    await server.close()


async def test_fetch_and_pin(tls_server: tuple[TestServer, str]) -> None:
    server, expected = tls_server
    assert server.port is not None
    assert await fetch_certificate_fingerprint("127.0.0.1", server.port) == expected
    url = str(server.make_url("/"))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(CertificateError):
            await PrusaConnect(session, url).health()
        pinned = PrusaConnect(session, url, fingerprint=expected.lower())
        assert (await pinned.health()).status == "ok"
        wrong = PrusaConnect(session, url, fingerprint="00" * 32)
        with pytest.raises(CertificateError) as err:
            await wrong.health()
        assert err.value.fingerprint == expected
        unverified = PrusaConnect(session, url, verify_ssl=False)
        assert (await unverified.health()).status == "ok"


async def test_fetch_unreachable() -> None:
    with pytest.raises(CannotConnectError):
        await fetch_certificate_fingerprint("127.0.0.1", 9, connect_timeout=2)
