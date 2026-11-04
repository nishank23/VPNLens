"""Bounded, per-worker API quota for the single-worker demo."""

from math import ceil
from time import monotonic


class ApiRateLimit:
    def __init__(self, per_client, total):
        self.per_client = per_client
        self.total = total
        self.window_end = monotonic() + 60
        self.used = 0
        self.clients: dict[str, int] = {}

    def retry_after(self, client: str) -> int | None:
        """Record an admitted request or return seconds until the window resets.

        Call on the app's event loop. No await occurs during the state update.
        The shared quota bounds the number of client keys held in memory.
        """
        now = monotonic()
        if now >= self.window_end:
            self.window_end = now + 60
            self.used = 0
            self.clients.clear()

        count = self.clients.get(client, 0)
        if count >= self.per_client or self.used >= self.total:
            return ceil(self.window_end - now)

        self.clients[client] = count + 1
        self.used += 1
        return None
