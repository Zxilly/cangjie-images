from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, BinaryIO

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from cangjie_images.config import USER_AGENT

_DEFAULT_TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    if exc is None:
        return
    print(
        f"[http] retry {state.attempt_number} after {type(exc).__name__}: {exc}",
        flush=True,
    )


_retry = retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.5, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
    before_sleep=_log_retry,
)


@contextmanager
def http_client(**overrides: Any) -> Iterator[httpx.Client]:
    params: dict[str, Any] = {
        "timeout": _DEFAULT_TIMEOUT,
        "headers": {"User-Agent": USER_AGENT, "Accept": "application/json"},
        "follow_redirects": True,
    }
    params.update(overrides)
    with httpx.Client(**params) as client:
        yield client


@_retry
def get_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    allow_404: bool = False,
) -> object | None:
    response = client.get(url, headers=headers)
    if allow_404 and response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


@_retry
def stream_download(client: httpx.Client, url: str, dest_fp: BinaryIO) -> None:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
            dest_fp.write(chunk)
