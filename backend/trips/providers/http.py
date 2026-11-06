"""Shared HTTP session: timeouts, retries on 429/5xx, and errors that never contain the URL.

Error messages must not include request URLs, because the TomTom key travels in the query string.
"""

from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

TIMEOUT_S = (5, 15)  # connect, read: fail fast rather than leave the user waiting
USER_AGENT = "weather-aware-truck-routing/0.1 (take-home demo)"


class ProviderError(Exception):
    """An outside API failed or answered something we cannot use. The message is safe to show."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def make_session(retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)) -> requests.Session:
    """429 is retried by default (TomTom's per-second limit clears quickly); Open-Meteo opts out."""
    retry = Retry(
        total=2,
        read=1,  # one retry after a slow answer
        backoff_factor=0.5,  # 0.5 s, then 1 s
        status_forcelist=retry_statuses,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=False,  # a rate limit can say "retry in 60 s"; better to fail with a message
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session.mount("https://", adapter)
    return session


def get_json(
    session: requests.Session, service: str, url: str, params: dict, timeout: tuple[float, float] = TIMEOUT_S
) -> tuple[int, object]:
    """GET and decode JSON. Returns (status, body); raises ProviderError on network/JSON failure."""
    try:
        response = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("%s request failed: %s", service, type(exc).__name__)
        raise ProviderError(f"{service} could not be reached. Please try again.") from None
    try:
        body = response.json()
    except ValueError:
        log.warning("%s returned non-JSON (HTTP %s)", service, response.status_code)
        raise ProviderError(f"{service} returned an unexpected answer (HTTP {response.status_code}).") from None
    return response.status_code, body
