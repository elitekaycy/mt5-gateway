"""In-process idempotency support for order placement."""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any, Callable, Mapping, Optional


class Decision(Enum):
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class StoredResponse:
    payload: dict[str, Any]
    status_code: int


@dataclass
class _Entry:
    fingerprint: str
    created_at: float
    response: Optional[StoredResponse] = None


class IdempotencyStore:
    """Thread-safe TTL cache that reserves keys before broker submission."""

    def __init__(
        self, ttl_seconds: float = 3600, clock: Callable[[], float] = time.monotonic
    ):
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = Lock()

    def begin(
        self, key: str, fingerprint: str
    ) -> tuple[Decision, Optional[StoredResponse]]:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(fingerprint, now)
                return Decision.NEW, None
            if entry.fingerprint != fingerprint:
                return Decision.CONFLICT, None
            if entry.response is None:
                return Decision.IN_PROGRESS, None
            return Decision.REPLAY, entry.response

    def complete(
        self, key: str, fingerprint: str, payload: dict[str, Any], status_code: int
    ) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.fingerprint != fingerprint:
                return
            entry.response = StoredResponse(payload, status_code)

    def abandon(self, key: str, fingerprint: str) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if (
                entry is not None
                and entry.fingerprint == fingerprint
                and entry.response is None
            ):
                del self._entries[key]

    def _purge_expired(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.created_at >= self._ttl_seconds
        ]
        for key in expired:
            del self._entries[key]


def request_fingerprint(data: Mapping[str, Any]) -> str:
    """Hash order intent independently of where the idempotency key was sent."""
    intent = dict(data)
    intent.pop("client_order_id", None)
    canonical = json.dumps(intent, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def magic_from_key(key: str) -> int:
    """Derive a stable non-zero uint32 ownership marker from a client key."""
    magic = int.from_bytes(
        hashlib.blake2s(key.encode("utf-8"), digest_size=4).digest(), "big"
    )
    return magic or 1
