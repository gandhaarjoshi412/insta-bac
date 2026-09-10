"""In-memory rate limiter for public authentication and pairing endpoints."""

import collections
import logging
import time
from typing import Dict, Deque
from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._records: Dict[str, Deque[float]] = collections.defaultdict(collections.deque)

    def is_allowed(self, client_key: str) -> bool:
        """Check if request from client_key is within allowed limit."""
        now = time.monotonic()
        cutoff = now - 60.0
        queue = self._records[client_key]

        # Purge entries older than 60 seconds
        while queue and queue[0] < cutoff:
            queue.popleft()

        if len(queue) >= self.requests_per_minute:
            return False

        queue.append(now)
        return True

    def check(self, request: Request, custom_key: str = "") -> None:
        """Enforce rate limit, raising 429 Too Many Requests if exceeded."""
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}:{custom_key}"
        if not self.is_allowed(key):
            logger.warning("Rate limit exceeded for client %s on %s", client_ip, request.url.path)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
            )


rate_limiter = InMemoryRateLimiter(requests_per_minute=settings.RATE_LIMIT_PER_MINUTE)
