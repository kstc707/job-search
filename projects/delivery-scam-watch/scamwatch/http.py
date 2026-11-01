"""Polite downloading shared by every collector.

- One identifying user-agent (the project's GitHub URL), never a personal email.
- A minimum gap between requests to the same host (the source's politeness limit).
- Retries with growing waits on time-outs, 429 "slow down" and 5xx errors, honouring a
  `Retry-After` header when the server sends one. Other 4xx errors fail at once: retrying a
  wrong request only adds load.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from .config import Settings
from .runlog import log

RETRY_STATUS = {429, 500, 502, 503, 504}


class Fetcher:
    def __init__(
        self,
        min_interval: float = 1.0,
        timeout: float = 60.0,
        max_tries: int = 5,
        sleep=time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.min_interval = min_interval
        self.max_tries = max_tries
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self.client = httpx.Client(
            timeout=timeout, follow_redirects=True, transport=transport, headers={"User-Agent": Settings().user_agent}
        )

    def _wait_turn(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        gap = time.monotonic() - self._last.get(host, -1e9)
        if gap < self.min_interval:
            self._sleep(self.min_interval - gap)
        self._last[host] = time.monotonic()

    def get(self, url: str, **kwargs) -> httpx.Response:
        delay = 2.0
        for attempt in range(1, self.max_tries + 1):
            self._wait_turn(url)
            try:
                resp = self.client.get(url, **kwargs)
            except httpx.TransportError as exc:  # time-outs, dropped connections
                problem = f"{type(exc).__name__}"
            else:
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp
                problem = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, min(float(retry_after), 300.0))
                if attempt == self.max_tries:
                    raise RuntimeError(f"{url} failed after {attempt} tries: {problem}")
            if attempt == self.max_tries:
                raise RuntimeError(f"{url} failed after {attempt} tries: {problem}")
            log("retry", url=url, attempt=attempt, problem=problem, wait_seconds=delay)
            self._sleep(delay)
            delay = min(delay * 2, 120.0)
        raise AssertionError("unreachable")

    def close(self) -> None:
        self.client.close()
