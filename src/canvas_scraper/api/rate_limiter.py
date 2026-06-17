"""Rate limiting for Canvas API requests."""

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimitInfo:
    """Information about current rate limit status."""

    remaining: int
    limit: int
    reset_at: float | None = None


class RateLimiter:
    """Rate limiter that respects Canvas API rate limits.

    Canvas uses a cost-based rate limiting system. Each request costs a certain
    number of points, and you have a budget that refills over time.
    """

    def __init__(self, min_remaining: int = 50, delay_seconds: float = 0.1):
        """Initialize the rate limiter.

        Args:
            min_remaining: Minimum remaining requests before slowing down.
            delay_seconds: Base delay between requests.
        """
        self.min_remaining = min_remaining
        self.delay_seconds = delay_seconds
        self._last_request_time: float = 0
        self._rate_limit_info: RateLimitInfo | None = None
        self._lock = threading.Lock()

    def update_from_response(self, response: Any) -> None:
        """Update rate limit info from API response headers.

        Args:
            response: Response object with headers.
        """
        headers = getattr(response, "headers", {})
        if not headers:
            return

        remaining = headers.get("X-Rate-Limit-Remaining")
        limit = headers.get("X-Rate-Limit-Limit")

        if remaining is not None and limit is not None:
            self._rate_limit_info = RateLimitInfo(
                remaining=int(float(remaining)),
                limit=int(float(limit)),
            )

    def wait_if_needed(self) -> None:
        """Wait if necessary to respect rate limits."""
        with self._lock:
            now = time.time()

            # Always maintain minimum delay between requests
            elapsed = now - self._last_request_time
            if elapsed < self.delay_seconds:
                time.sleep(self.delay_seconds - elapsed)

            # If we're running low on rate limit budget, slow down more
            if self._rate_limit_info:
                if self._rate_limit_info.remaining < self.min_remaining:
                    # Slow down significantly when approaching limit
                    extra_delay = (self.min_remaining - self._rate_limit_info.remaining) * 0.1
                    time.sleep(min(extra_delay, 5.0))  # Cap at 5 seconds

                if self._rate_limit_info.remaining < 10:
                    # Very low - wait longer
                    time.sleep(2.0)

            self._last_request_time = time.time()

    @property
    def remaining(self) -> int | None:
        """Get remaining rate limit budget."""
        if self._rate_limit_info:
            return self._rate_limit_info.remaining
        return None
