"""Tests for the extract step (src/extract.py)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import requests

from src.extract import ExtractError, extract_from_url, fetch_url, read_raw_csv

from .conftest import FakeResponse


class TestFetchUrl:
    def test_reads_a_file_url(self, raw_url, sample_raw):
        assert fetch_url(raw_url) == sample_raw.read_bytes()

    def test_missing_file_url_raises(self, tmp_path):
        with pytest.raises(ExtractError, match="Local file not found"):
            fetch_url((tmp_path / "nope.csv").as_uri())

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ExtractError, match="Unsupported URL scheme"):
            fetch_url("ftp://example.com/data.csv")

    def test_http_uses_requests_with_a_timeout(self, fake_get):
        response = FakeResponse(content=b"a,b\n1,2\n")
        calls = fake_get(response)

        assert fetch_url("https://example.com/data.csv", timeout=7) == b"a,b\n1,2\n"
        assert calls["timeout"] == 7
        assert "etl-pipeline" in calls["headers"]["User-Agent"]
        assert response.raise_for_status_called is True

    def test_http_error_status_raises(self, fake_get):
        error = requests.HTTPError("404 Client Error")
        fake_get(FakeResponse(content=b"<html>nope</html>", raise_error=error))

        with pytest.raises(ExtractError, match="failed"):
            fetch_url("https://example.com/missing.csv")

    def test_timeout_is_reported_clearly(self, fake_get):
        fake_get(requests.Timeout("too slow"))

        with pytest.raises(ExtractError, match="timed out after 12s"):
            fetch_url("https://example.com/slow.csv", timeout=12)

    def test_empty_body_raises(self, fake_get):
        fake_get(FakeResponse(content=b""))

        with pytest.raises(ExtractError, match="empty body"):
            fetch_url("https://example.com/empty.csv")


class TestExtractFromUrl:
    def test_saves_the_file_and_reports_metadata(self, raw_url, tmp_path, sample_raw):
        destination = tmp_path / "sub" / "dir" / "raw.csv"

        result = extract_from_url(raw_url, destination)

        assert destination.is_file()
        assert result.path == destination
        assert result.size_bytes == sample_raw.stat().st_size
        assert result.sha256 == hashlib.sha256(sample_raw.read_bytes()).hexdigest()
        assert result.downloaded_at.tzinfo is not None

    def test_creates_missing_parent_directories(self, raw_url, tmp_path):
        destination = tmp_path / "a" / "b" / "c" / "raw.csv"
        extract_from_url(raw_url, destination)
        assert destination.is_file()

    def test_overwrites_an_existing_file(self, raw_url, tmp_path):
        destination = tmp_path / "raw.csv"
        destination.write_text("stale content", encoding="utf-8")

        extract_from_url(raw_url, destination)

        assert "stale content" not in destination.read_text(encoding="utf-8")

    def test_blank_payload_raises_and_writes_nothing(self, tmp_path):
        destination = tmp_path / "raw.csv"
        blank = tmp_path / "blank.csv"
        blank.write_text("   \n  ", encoding="utf-8")

        with pytest.raises(ExtractError, match="blank"):
            extract_from_url(blank.as_uri(), destination)

        assert not destination.exists()

    def test_failed_download_leaves_previous_file_untouched(self, fake_get, tmp_path):
        destination = tmp_path / "raw.csv"
        destination.write_text("good old data", encoding="utf-8")
        fake_get(requests.Timeout("too slow"))

        with pytest.raises(ExtractError):
            extract_from_url("https://example.com/slow.csv", destination)

        assert destination.read_text(encoding="utf-8") == "good old data"

    def test_no_temp_file_is_left_behind(self, raw_url, tmp_path):
        destination = tmp_path / "raw.csv"
        extract_from_url(raw_url, destination)

        assert [p.name for p in tmp_path.iterdir()] == ["raw.csv"]


class TestReadRawCsv:
    def test_reads_the_sample(self, sample_raw):
        frame = read_raw_csv(sample_raw)
        assert len(frame) == 8
        assert "Country/Region" in frame.columns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ExtractError, match="not found"):
            read_raw_csv(tmp_path / "absent.csv")
