"""
extract.py — Step 1 of the ETL pipeline: EXTRACT.

Downloads the raw dataset and saves it to data/raw/ so the Transform step can
work on a file instead of a network connection.

Design choices worth knowing about:

* A timeout is always passed to requests.get(), so a hung server cannot block
  the pipeline forever.
* raise_for_status() turns HTTP 4xx/5xx into a clear exception instead of
  silently writing an HTML error page into data/raw/.
* The body is written to a temporary file first and then moved into place
  (os.replace), so an interrupted run can never leave a half-written CSV that
  the next run would happily treat as valid input.
* A SHA-256 checksum of the body is returned so callers can tell whether the
  upstream data actually changed between runs.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import pandas as pd
import requests

from . import config

__all__ = [
    "ExtractError",
    "ExtractResult",
    "fetch_url",
    "extract_from_url",
    "read_raw_csv",
]


class ExtractError(RuntimeError):
    """Raised when the raw data cannot be downloaded or saved."""


@dataclass(frozen=True)
class ExtractResult:
    """What the extract step produced, for logging and tests."""

    path: Path
    url: str
    size_bytes: int
    sha256: str
    downloaded_at: datetime

    def __str__(self) -> str:
        return (
            f"{self.path} ({self.size_bytes:,} bytes, "
            f"sha256={self.sha256[:12]}...)"
        )


def _fetch_http(url: str, timeout: int) -> bytes:
    """Download a URL over http(s) and return the response body."""
    headers = {"User-Agent": config.USER_AGENT}
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ExtractError(
            f"Download from {url} timed out after {timeout}s. "
            "Try again or raise the timeout."
        ) from exc
    except requests.RequestException as exc:
        raise ExtractError(f"Download from {url} failed: {exc}") from exc

    if not response.content:
        raise ExtractError(f"Download from {url} returned an empty body.")
    return response.content


def _fetch_file(url: str) -> bytes:
    """Read a local file referenced with a file:// URL.

    This keeps the pipeline runnable offline (and makes the tests fast) while
    still exercising exactly the same extract code path.
    """
    parsed = urlparse(url)
    path = Path(url2pathname(unquote(parsed.path)))
    if not path.is_file():
        raise ExtractError(f"Local file not found: {path}")
    return path.read_bytes()


def fetch_url(url: str, timeout: int = config.REQUEST_TIMEOUT_SECONDS) -> bytes:
    """Return the raw bytes at `url`, supporting http(s):// and file://."""
    scheme = urlparse(url).scheme
    if scheme in ("http", "https"):
        return _fetch_http(url, timeout)
    if scheme == "file":
        return _fetch_file(url)
    raise ExtractError(
        f"Unsupported URL scheme {scheme!r} in {url!r}. "
        "Use http://, https:// or file://."
    )


def _write_atomically(path: Path, payload: bytes) -> None:
    """Write `payload` to `path` without risking a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".part")
    try:
        temp_path.write_bytes(payload)
        os.replace(temp_path, path)
    finally:
        # os.replace() removes the temp file, so this is a no-op on success.
        if temp_path.exists():
            temp_path.unlink()


def extract_from_url(
    url: str = config.SOURCE_URL,
    output_path: Path | str = config.DEFAULT_RAW_PATH,
    timeout: int = config.REQUEST_TIMEOUT_SECONDS,
) -> ExtractResult:
    """Download `url` and save it to `output_path`. Returns an ExtractResult."""
    destination = Path(output_path)
    payload = fetch_url(url, timeout=timeout)

    if not payload.strip():
        raise ExtractError(f"Download from {url} was blank; nothing to save.")

    _write_atomically(destination, payload)

    return ExtractResult(
        path=destination,
        url=url,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        downloaded_at=datetime.now(timezone.utc),
    )


def read_raw_csv(path: Path | str) -> pd.DataFrame:
    """Read a raw CSV into a DataFrame (used by transform and the tests).

    A file that exists but cannot be parsed (empty, truncated, or not UTF-8
    text) raises ExtractError, so callers never have to catch pandas' own
    exceptions on top of ours.
    """
    source = Path(path)
    if not source.is_file():
        raise ExtractError(f"Raw file not found: {source}")
    try:
        return pd.read_csv(source)
    except pd.errors.EmptyDataError as exc:
        raise ExtractError(f"Raw file is empty: {source}") from exc
    except UnicodeDecodeError as exc:
        raise ExtractError(f"Raw file is not valid UTF-8 text: {source}") from exc
    except pd.errors.ParserError as exc:
        raise ExtractError(f"Could not parse raw CSV {source}: {exc}") from exc
    except OSError as exc:
        raise ExtractError(f"Could not read raw file {source}: {exc}") from exc
