"""
app/services/token_store.py
────────────────────────────
Where issued refresh tokens are remembered, so that rotation means something.

WHY THIS EXISTS AS A MODULE
Refresh tokens were held in a plain module-level dict. That is correct for a
single process and wrong for every deployment that runs more than one, which is
every deployment here: the image starts uvicorn with `WEB_CONCURRENCY` workers,
and the platform may run several instances of the service.

The failure is not theoretical and not graceful. A token issued by worker A is
absent from worker B's dict, so a refresh that happens to land on B is answered
"Refresh token has been revoked" and the person is signed out — at random, on
roughly half of all refreshes with two workers, with nothing in the logs to
distinguish it from a genuine replay.

So the store is an explicit interface with two backends:

    Redis   — shared across workers and instances. The correct one.
    memory  — per process. Used only when Redis is unreachable, which is also
              the case in the test suite and in a bare `uvicorn app.main:app`.

Degrading to memory keeps single-worker deployments and tests working rather
than making Redis a hard dependency of logging in. It is logged loudly, because
in a multi-worker deployment it is a correctness problem, not a performance one.

WHAT IS STORED
The SHA-256 of the token's `jti`, mapped to the owning user id. Never the token
itself: a dump of this store must not be usable to authenticate. Entries carry
the token's own lifetime as a TTL, so expired grants disappear on their own
rather than accumulating for the life of the process.
"""

from __future__ import annotations

import time
from typing import Optional, Protocol

from app.core.logging import get_logger
from app.middleware.rate_limit import RATE_LIMIT_STORAGE_URI, REDIS_AVAILABLE

logger = get_logger(__name__)

_KEY_PREFIX = "refresh:"


class _Backend(Protocol):
    async def put(self, key: str, user_id: str, ttl_seconds: int) -> None: ...
    async def take(self, key: str) -> Optional[str]: ...
    async def drop(self, key: str) -> None: ...


class _MemoryBackend:
    """Per-process store. Correct only when there is exactly one process."""

    def __init__(self) -> None:
        # hashed_jti -> (user_id, expires_at_epoch)
        self._entries: dict[str, tuple[str, float]] = {}

    def _prune(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._entries.items() if exp <= now]
        for key in expired:
            self._entries.pop(key, None)

    async def put(self, key: str, user_id: str, ttl_seconds: int) -> None:
        now = time.time()
        self._prune(now)
        self._entries[key] = (user_id, now + ttl_seconds)

    async def take(self, key: str) -> Optional[str]:
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        user_id, expires_at = entry
        return user_id if expires_at > time.time() else None

    async def drop(self, key: str) -> None:
        self._entries.pop(key, None)


class _RedisBackend:
    """
    Shared store. The only backend under which rotation is actually enforced
    across workers.

    `take` must be atomic: two concurrent refreshes presenting the same token
    must not both succeed, because that is precisely the replay that rotation
    exists to catch. GETDEL does the read and the delete in one server-side
    operation; a GET followed by a DELETE would leave a window between them.
    """

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis_asyncio

        self._client = redis_asyncio.from_url(
            url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )

    async def put(self, key: str, user_id: str, ttl_seconds: int) -> None:
        await self._client.set(key, user_id, ex=ttl_seconds)

    async def take(self, key: str) -> Optional[str]:
        return await self._client.getdel(key)

    async def drop(self, key: str) -> None:
        await self._client.delete(key)


class RefreshTokenStore:
    """
    Records which refresh tokens are currently valid.

    Every method takes the *hash* of a jti, never a token. The caller does the
    hashing, so a raw token never reaches this module at all.
    """

    def __init__(self) -> None:
        self._backend: Optional[_Backend] = None
        self._degraded = False

    def _resolve(self) -> _Backend:
        if self._backend is not None:
            return self._backend

        if REDIS_AVAILABLE and not self._degraded:
            try:
                self._backend = _RedisBackend(RATE_LIMIT_STORAGE_URI)
                return self._backend
            except Exception as exc:  # noqa: BLE001 — any failure means unusable
                self._fall_back(type(exc).__name__)

        self._backend = _MemoryBackend()
        return self._backend

    def _fall_back(self, reason: str) -> None:
        """Drop to the per-process backend and say so, once."""
        if not self._degraded:
            logger.warning(
                "refresh_token_store_degraded",
                reason=reason,
                detail=(
                    "Redis unusable; refresh tokens are held per process. "
                    "With more than one worker or instance, refreshes that land "
                    "on another process will be rejected."
                ),
            )
        self._degraded = True
        self._backend = _MemoryBackend()

    async def _call(self, operation: str, key: str, *args):
        backend = self._resolve()
        try:
            return await getattr(backend, operation)(key, *args)
        except Exception as exc:  # noqa: BLE001 — Redis failed mid-flight
            if isinstance(backend, _MemoryBackend):
                raise
            self._fall_back(type(exc).__name__)
            return await getattr(self._resolve(), operation)(key, *args)

    async def issue(self, hashed_jti: str, user_id: str, ttl_seconds: int) -> None:
        """Record a newly issued refresh token."""
        await self._call("put", _KEY_PREFIX + hashed_jti, user_id, ttl_seconds)

    async def consume(self, hashed_jti: str) -> Optional[str]:
        """
        Spend a refresh token: return its owner and invalidate it in one step.

        Returns None when the token is unknown, already spent or expired — the
        three cases the caller must treat identically.
        """
        return await self._call("take", _KEY_PREFIX + hashed_jti)

    async def revoke(self, hashed_jti: str) -> None:
        """Invalidate a refresh token without issuing anything (logout)."""
        await self._call("drop", _KEY_PREFIX + hashed_jti)

    def reset_for_tests(self) -> None:
        """Discard all state. Used by the test suite between cases."""
        self._backend = None
        self._degraded = False


#: Process-wide singleton. Import this, not the classes above.
refresh_token_store = RefreshTokenStore()
