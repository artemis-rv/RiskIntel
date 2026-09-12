"""
app/tests/test_deployment_config.py
────────────────────────────────────
The behaviour that only matters once the application is deployed behind a
managed platform: the shape of the connection string it is handed, where issued
refresh tokens are remembered, and which address it believes a request came
from.

Each test here corresponds to a fault that a local run cannot produce and a
deployment produces immediately.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.middleware.rate_limit import _get_client_ip
from app.services.token_store import RefreshTokenStore, _MemoryBackend

_VALID_SECRET = "a" * 48


def _settings(database_url: str) -> Settings:
    return Settings(DATABASE_URL=database_url, JWT_SECRET_KEY=_VALID_SECRET)


# ── Connection string normalisation ──────────────────────────────────────────
# Render supplies `postgresql://…`. SQLAlchemy reads the scheme as the driver,
# so without translation it selects psycopg2, which is not installed, and the
# service dies on its first database call.


def test_plain_postgresql_url_gains_the_asyncpg_dialect() -> None:
    settings = _settings("postgresql://user:pw@host:5432/db")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pw@host:5432/db"


def test_legacy_postgres_scheme_is_also_translated() -> None:
    settings = _settings("postgres://user:pw@host:5432/db")
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_an_explicit_dialect_is_left_alone() -> None:
    url = "postgresql+asyncpg://user:pw@host:5432/db"
    assert _settings(url).DATABASE_URL == url


def test_sslmode_is_translated_to_the_spelling_asyncpg_accepts() -> None:
    # asyncpg rejects libpq's `sslmode` outright, so an external connection
    # string pasted from a dashboard would fail to connect.
    settings = _settings("postgresql://user:pw@host:5432/db?sslmode=require")
    assert "sslmode" not in settings.DATABASE_URL
    assert "ssl=require" in settings.DATABASE_URL


def test_permissive_sslmode_values_are_dropped_rather_than_forced() -> None:
    settings = _settings("postgresql://user:pw@host:5432/db?sslmode=prefer")
    assert "sslmode" not in settings.DATABASE_URL
    assert "ssl=" not in settings.DATABASE_URL


# ── Refresh token store ──────────────────────────────────────────────────────


def _store() -> RefreshTokenStore:
    store = RefreshTokenStore()
    # Pin the backend: this suite is about the store's contract, not about
    # whether a Redis happens to be running on the machine executing it.
    store._backend = _MemoryBackend()  # noqa: SLF001 — deliberate, test-local
    return store


@pytest.mark.asyncio
async def test_a_token_can_be_spent_exactly_once() -> None:
    store = _store()
    await store.issue("hash-a", "user-1", 3600)

    assert await store.consume("hash-a") == "user-1"
    # The second presentation is the replay that rotation exists to catch.
    assert await store.consume("hash-a") is None


@pytest.mark.asyncio
async def test_concurrent_use_of_one_token_yields_a_single_winner() -> None:
    store = _store()
    await store.issue("hash-b", "user-2", 3600)

    results = await asyncio.gather(*(store.consume("hash-b") for _ in range(8)))

    assert [r for r in results if r is not None] == ["user-2"]


@pytest.mark.asyncio
async def test_revocation_makes_a_token_unusable() -> None:
    store = _store()
    await store.issue("hash-c", "user-3", 3600)
    await store.revoke("hash-c")

    assert await store.consume("hash-c") is None


@pytest.mark.asyncio
async def test_an_expired_token_is_not_honoured() -> None:
    store = _store()
    await store.issue("hash-d", "user-4", -1)

    assert await store.consume("hash-d") is None


@pytest.mark.asyncio
async def test_an_unknown_token_is_refused() -> None:
    assert await _store().consume("never-issued") is None


# ── Client address derivation ────────────────────────────────────────────────
# The address decides which bucket the rate limiter counts against and what is
# written into the download audit trail. A client that can choose it can walk
# around the first and poison the second.


def _request(peer: str, forwarded: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/releases",
            "raw_path": b"/api/v1/releases",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 51234),
            "server": ("api", 8080),
        }
    )


def test_a_forwarded_header_from_an_untrusted_peer_is_ignored() -> None:
    # Anyone can send this header. Honouring it from a direct connection lets a
    # caller mint a fresh rate-limit bucket per request.
    assert _get_client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_a_forwarded_chain_from_a_trusted_peer_yields_the_real_client() -> None:
    # The proxy appends, so the rightmost address that is not ours is the one
    # that actually connected to it. Taking the leftmost would take the value
    # the client prepended.
    request = _request("127.0.0.1", "1.2.3.4, 198.51.100.7")
    assert _get_client_ip(request) == "198.51.100.7"


def test_a_request_with_no_forwarded_header_uses_the_peer() -> None:
    assert _get_client_ip(_request("127.0.0.1", None)) == "127.0.0.1"
