"""
Shared pytest fixtures.

The tests never touch the network or the real data/ folder: they run against
the small CSV in tests/fixtures/ and temporary directories, so the suite is
fast, offline and deterministic.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src import config

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_RAW = FIXTURE_DIR / "sample_confirmed.csv"
SAMPLE_DEATHS = FIXTURE_DIR / "sample_deaths.csv"

# The fixture has 8 locations x 4 dates = 32 melted rows, of which
# 4 have a blank country, 2 hold a negative count, and 4 are duplicates.
EXPECTED_MELTED_ROWS = 32
EXPECTED_CLEAN_ROWS = 22
EXPECTED_COUNTRIES = 6

# The deaths fixture has the same 8 locations, so the two can be joined.
# 4 rows have a blank country, 1 holds a negative count, 4 are duplicates.
EXPECTED_DEATHS_CLEAN_ROWS = 23


@pytest.fixture
def sample_raw() -> Path:
    """Path to the messy sample raw CSV."""
    return SAMPLE_RAW


@pytest.fixture
def raw_url(sample_raw: Path) -> str:
    """A file:// URL for the sample, so extract runs offline."""
    return sample_raw.as_uri()


@pytest.fixture
def sample_deaths() -> Path:
    """Path to the messy sample deaths CSV."""
    return SAMPLE_DEATHS


@pytest.fixture
def deaths_url(sample_deaths: Path) -> str:
    """A file:// URL for the deaths sample."""
    return sample_deaths.as_uri()


@pytest.fixture
def clean_csv(tmp_path: Path) -> Path:
    """A small processed CSV, in the exact format the load step expects."""
    path = tmp_path / "clean.csv"
    path.write_text(
        "date,country,province,latitude,longitude,confirmed,new_cases\n"
        "2020-01-22,Albania,Unknown,41.15,20.17,0,0\n"
        "2020-01-23,Albania,Unknown,41.15,20.17,2,2\n"
        "2020-01-22,Australia,Springfield,-37.84,144.99,0,0\n"
        "2020-01-23,Australia,Springfield,-37.84,144.99,1,1\n",
        encoding="utf-8",
    )
    return path


class FakeResponse:
    """A stand-in for requests.Response, so extract can be tested offline."""

    def __init__(
        self,
        content: bytes = b"",
        status_code: int = 200,
        raise_error: Exception | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self._raise_error = raise_error
        self.raise_for_status_called = False

    def raise_for_status(self) -> None:
        self.raise_for_status_called = True
        if self._raise_error is not None:
            raise self._raise_error


@pytest.fixture
def fake_get(monkeypatch):
    """Replace requests.get with a factory returning a FakeResponse."""

    def _install(response: FakeResponse | Exception):
        calls: dict = {}

        def _get(url, timeout=None, headers=None):
            calls["url"] = url
            calls["timeout"] = timeout
            calls["headers"] = headers
            if isinstance(response, Exception):
                raise response
            return response

        import src.extract as extract_module

        monkeypatch.setattr(extract_module.requests, "get", _get)
        return calls

    return _install


@pytest.fixture
def offline_datasets(tmp_path, monkeypatch) -> dict[str, config.Dataset]:
    """Point both registered datasets at the fixtures and tmp_path."""
    sources = {"confirmed": SAMPLE_RAW, "deaths": SAMPLE_DEATHS}
    specs = {}
    for name, source in sources.items():
        spec = dataclasses.replace(
            config.DATASETS[name],
            source_url=source.as_uri(),
            raw_path=tmp_path / "raw" / f"{name}.csv",
            processed_path=tmp_path / "processed" / f"{name}.csv",
        )
        monkeypatch.setitem(config.DATASETS, name, spec)
        specs[name] = spec
    return specs
