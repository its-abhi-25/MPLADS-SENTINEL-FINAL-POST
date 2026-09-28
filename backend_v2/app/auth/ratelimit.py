"""
Rate limits (BLUEPRINT.md §11: "Applied to login, copilot and search
endpoints").

A sliding one-minute window per (bucket, key), in process memory. Keys are
the client address and, where a caller is authenticated or names an
account, that identity too -- so one client can't exhaust a user's login
attempts from many addresses without also hitting the per-username limit.
A request over the limit gets 429 with Retry-After.

In-process state is correct for a single API process (the compose
deployment). Running several API processes needs a shared store (for
example Redis) behind the same interface -- documented in docs/security.md.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..core.config import get_settings

WINDOW = 60.0


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, bucket: str, key: str, limit: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] <= now - WINDOW:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, math.ceil(q[0] + WINDOW - now))
                raise HTTPException(
                    status_code=429,
                    detail=f"rate limit exceeded for {bucket}: {limit} requests per minute",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)


LIMITER = RateLimiter()


def client_key(request: Request) -> str:
    if get_settings().trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(bucket: str, request: Request, *extra_keys: str) -> None:
    s = get_settings()
    per_minute = {
        "login": s.rate_limit_login_per_minute,
        "chat": s.rate_limit_chat_per_minute,
        "search": s.rate_limit_search_per_minute,
    }[bucket]
    LIMITER.hit(bucket, f"ip:{client_key(request)}", per_minute)
    for k in extra_keys:
        if k:
            LIMITER.hit(bucket, k, per_minute)
