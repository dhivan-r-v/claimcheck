"""In-memory result cache and rate limiter, shared by the web API and the Telegram bot."""
import hashlib
import time
from collections import OrderedDict, defaultdict, deque

from . import config


def cache_key(text: str, image: bytes | None = None) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode() + (image or b"")).hexdigest()


class ResultCache:
    """Repeated checks of the same message (demo examples, judges, viral forwards) cost nothing."""

    def __init__(self, size: int = config.CACHE_SIZE):
        self.size = size
        self._data: OrderedDict[str, dict] = OrderedDict()

    def get(self, key: str) -> dict | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, result: dict) -> None:
        self._data[key] = result
        while len(self._data) > self.size:
            self._data.popitem(last=False)


class RateLimiter:
    def __init__(self, per_hour: int = config.RATE_LIMIT_PER_HOUR):
        self.per_hour = per_hour
        self._hits: dict[str, deque] = defaultdict(deque)

    def limited(self, who: str) -> bool:
        """Record a hit for `who`; True if they are over the hourly limit."""
        now, q = time.time(), self._hits[who]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= self.per_hour:
            return True
        q.append(now)
        return False


results = ResultCache()
limiter = RateLimiter()
