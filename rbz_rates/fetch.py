"""Polite HTTP fetching with retries."""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

USER_AGENT = "rbz-rates/0.1 (open-source exchange rate mirror)"
DELAY_SECONDS = 2.0  # between requests; RBZ is a small Joomla site


class NotFound(Exception):
    """The URL returned 404 (e.g. no PDF for that day: weekend, holiday, not yet published)."""


class Blocked(Exception):
    """The site redirected us to another host, e.g. a bot-protection challenge."""


@dataclass
class FetchedPDF:
    content: bytes | None        # None: server said 304 Not Modified
    etag: str | None = None
    last_modified: str | None = None


class Fetcher:
    def __init__(self, timeout: float = 30.0, retries: int = 3):
        self.client = httpx.Client(timeout=timeout, follow_redirects=True,
                                   headers={"User-Agent": USER_AGENT})
        self.retries = retries
        self._last = 0.0

    def get(self, url: str, headers: dict | None = None) -> httpx.Response:
        for attempt in range(1, self.retries + 1):
            wait = DELAY_SECONDS - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.client.get(url, headers=headers)
                if resp.status_code < 500:
                    return resp
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            time.sleep(2 ** attempt)
        return resp

    def _checked(self, url: str, headers: dict | None = None) -> httpx.Response:
        resp = self.get(url, headers)
        if resp.url.host != urlsplit(url).hostname:
            raise Blocked(f"{url} redirected to {resp.url.host}")
        if resp.status_code == 404:
            raise NotFound(url)
        if resp.status_code != 304:  # 304 is the expected answer to a conditional request
            resp.raise_for_status()
        return resp

    def text(self, url: str) -> str:
        return self._checked(url).text

    def pdf(self, url: str, etag: str | None = None, last_modified: str | None = None) -> FetchedPDF:
        """Fetch a PDF into memory (callers must not write it to disk).

        Pass the etag / last_modified from a previous fetch to make it a
        conditional request: if the file is unchanged the server answers 304
        and nothing is downloaded (content is None).
        """
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        resp = self._checked(url, headers)
        validators = dict(etag=resp.headers.get("etag", etag),
                          last_modified=resp.headers.get("last-modified", last_modified))
        if resp.status_code == 304:
            return FetchedPDF(None, **validators)
        if not resp.content.startswith(b"%PDF"):
            raise ValueError(f"{url} did not return a PDF (got {resp.headers.get('content-type')})")
        return FetchedPDF(resp.content, **validators)
