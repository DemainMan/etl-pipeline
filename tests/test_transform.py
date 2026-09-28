"""Tests for the transform step (src/transform.py)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.transform import (
    TransformError,
    ValidationError,
    add_new_cases,
    coerce_numbers,
    drop_duplicates,
    drop_invalid_rows,
    normalise_text,
    parse_dates,
    read_raw,
    rename_columns,
    transform,
    validate,
    wide_to_long,
)

from .conftest import EXPECTED_CLEAN_ROWS, EXPECTED_COUNTRIES, EXPECTED_MELTED_ROWS


def long_frame(**overrides) -> pd.DataFrame:
    """A minimal already-melted frame, for testing the single steps."""
    data = {
        "date": [datetime(2020, 1, 22), datetime(2020, 1, 23)],
        "country": ["Albania", "Albania"],
        "province": ["Unknown", "Unknown"],
        "latitude": [41.15, 41.15],
        "longitude": [20.17, 20.17],
        "confirmed": [0, 2],
    }
    data.update(overrides)
    return pd.DataFrame(data)


class TestReadRaw:
    def test_reads_the_sample(self, sample_raw):
        assert len(read_raw(sample_raw)) == 8

    def test_missing_expected_column_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("Country/Region,Lat,Long,1/22/20\nAlbania,1,2,0\n", encoding="utf-8")

        with pytest.raises(TransformError, match="missing expected column"):
            read_raw(bad)

    def test_empty_file_raises(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text(
            "Province/State,Country/Region,Lat,Long\n", encoding="utf-8"
        )

        with pytest.raises(TransformError, match="is empty"):
            read_raw(empty)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(TransformError):
            read_raw(tmp_path / "absent.csv")


class TestRenameColumns:
    def test_renames_and_keeps_date_columns(self, sample_raw):
        renamed = rename_columns(read_raw(sample_raw))

        assert list(renamed.columns[:4]) == config.RAW_ID_COLUMNS
        assert "Country/Region" not in renamed.columns
        assert "1/22/20" in renamed.columns


class TestNormaliseText:
    def test_blank_province_becomes_unknown(self, sample_raw):
        cleaned = normalise_text(rename_columns(read_raw(sample_raw)))

        assert (cleaned["province"] == config.UNKNOWN_PROVINCE).sum() == 6
        assert not cleaned["province"].isna().any()

    def test_whitespace_is_stripped_from_names(self, sample_raw):
        cleaned = normalise_text(rename_columns(read_raw(sample_raw)))
        countries = set(cleaned["country"])

        assert "Whitespace Land" in countries
        assert "  Whitespace Land  " not in countries

    def test_whitespace_only_province_becomes_unknown(self, sample_raw):
        cleaned = normalise_text(rename_columns(read_raw(sample_raw)))
        row = cleaned[cleaned["country"] == "Whitespace Land"].iloc[0]

        assert row["province"] == config.UNKNOWN_PROVINCE


class TestWideToLong:
    def test_produces_one_row_per_day(self, sample_raw):
        melted = wide_to_long(normalise_text(rename_columns(read_raw(sample_raw))))

        assert len(melted) == EXPECTED_MELTED_ROWS
        assert sorted(melted["date"].unique()) == [
            "1/22/20",
            "1/23/20",
            "1/24/20",
            "1/25/20",
        ]

    def test_raises_when_no_date_columns_exist(self):
        no_dates = pd.DataFrame(
            {
                "province": ["Unknown"],
                "country": ["Albania"],
                "latitude": [41.15],
                "longitude": [20.17],
            }
        )
        with pytest.raises(TransformError, match="No date columns"):
            wide_to_long(no_dates)


class TestParseDates:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("1/22/20", datetime(2020, 1, 22)),
            ("12/31/21", datetime(2021, 12, 31)),
            ("1/1/2020", datetime(2020, 1, 1)),
            ("2020-03-09", datetime(2020, 3, 9)),
        ],
    )
    def test_parses_the_known_formats(self, label, expected):
        parsed = parse_dates(pd.DataFrame({"date": [label]}))
        assert parsed["date"].iloc[0] == expected

    def test_unparseable_label_becomes_null(self):
        parsed = parse_dates(pd.DataFrame({"date": ["not-a-date"]}))
        assert pd.isna(parsed["date"].iloc[0])

    def test_non_string_label_becomes_null(self):
        parsed = parse_dates(pd.DataFrame({"date": [20200122]}))
        assert pd.isna(parsed["date"].iloc[0])


class TestCoerceNumbers:
    def test_non_numeric_values_become_null(self):
        frame = long_frame()
        frame["confirmed"] = ["0", "two"]

        coerced = coerce_numbers(frame)

        assert coerced["confirmed"].iloc[0] == 0
        assert pd.isna(coerced["confirmed"].iloc[1])

    def test_coordinates_become_numeric(self):
        frame = long_frame(latitude=["41.15", "41.15"], longitude=["20.17", "20.17"])
        coerced = coerce_numbers(frame)

        assert coerced["latitude"].dtype.kind == "f"
        assert coerced["longitude"].dtype.kind == "f"


class TestDropInvalidRows:
    def test_counts_each_reason(self):
        frame = pd.DataFrame(
            {
                "date": [None, datetime(2020, 1, 22), datetime(2020, 1, 22), datetime(2020, 1, 22), datetime(2020, 1, 22)],
                "country": ["Albania", "", "Albania", "Albania", "Albania"],
                "confirmed": [1, 1, -3, None, 4],
            }
        )

        cleaned, dropped = drop_invalid_rows(frame)

        assert len(cleaned) == 1
        assert dropped == {
            "missing_date": 1,
            "missing_country": 1,
            "missing_count": 1,
            "negative_count": 1,
        }

    def test_keeps_zero_counts(self):
        frame = long_frame(confirmed=[0, 0])
        cleaned, _ = drop_invalid_rows(frame)
        assert len(cleaned) == 2


class TestDropDuplicates:
    def test_keeps_the_last_occurrence(self):
        frame = pd.DataFrame(
            {
                "date": [datetime(2020, 1, 22)] * 2,
                "country": ["Albania", "Albania"],
                "province": ["Unknown", "Unknown"],
                "confirmed": [1, 99],
            }
        )

        cleaned, removed = drop_duplicates(frame)

        assert removed == 1
        assert cleaned["confirmed"].iloc[0] == 99

    def test_same_key_in_different_provinces_is_kept(self):
        frame = pd.DataFrame(
            {
                "date": [datetime(2020, 1, 22)] * 2,
                "country": ["Australia"] * 2,
                "province": ["Queensland", "Victoria"],
                "confirmed": [1, 2],
            }
        )
        cleaned, removed = drop_duplicates(frame)

        assert removed == 0
        assert len(cleaned) == 2


class TestAddNewCases:
    def test_computes_the_day_over_day_change(self):
        frame = pd.DataFrame(
            {
                "date": [
                    datetime(2020, 1, 22),
                    datetime(2020, 1, 23),
                    datetime(2020, 1, 24),
                ],
                "country": ["Albania"] * 3,
                "province": ["Unknown"] * 3,
                "latitude": [41.15] * 3,
                "longitude": [20.17] * 3,
                "confirmed": [10, 15, 8],
            }
        )
        assert list(add_new_cases(frame)["new_cases"]) == [0, 5, -7]

    def test_keeps_groups_separate(self):
        frame = pd.DataFrame(
            {
                "date": [datetime(2020, 1, 22)] * 2 + [datetime(2020, 1, 22)] * 2,
                "country": ["Albania"] * 2 + ["Australia"] * 2,
                "province": ["Unknown"] * 2 + ["Victoria"] * 2,
                "confirmed": [1, 2, 100, 150],
            }
        )
        enriched = add_new_cases(frame)

        # Each place starts a fresh series, so both get a leading 0.
        assert list(enriched.sort_values("country")["new_cases"]) == [0, 1, 0, 50]


class TestValidate:
    def test_accepts_good_data(self):
        validate(add_new_cases(long_frame()))

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="no rows"):
            validate(add_new_cases(long_frame()).iloc[0:0])

    def test_rejects_missing_column(self):
        with pytest.raises(ValidationError, match="missing the 'country' column"):
            validate(long_frame().drop(columns=["country"]))

    def test_rejects_nulls_in_required_columns(self):
        frame = add_new_cases(long_frame())
        frame.loc[0, "country"] = None

        with pytest.raises(ValidationError, match="1 null value"):
            validate(frame)

    def test_rejects_negative_counts(self):
        with pytest.raises(ValidationError, match="negative value"):
            validate(add_new_cases(long_frame(confirmed=[-1, 2])))

    def test_rejects_duplicates_on_the_key(self):
        frame = add_new_cases(long_frame())
        duplicated = pd.concat([frame, frame], ignore_index=True)

        with pytest.raises(ValidationError, match="duplicate row"):
            validate(duplicated)


class TestTransform:
    @pytest.fixture
    def result(self, sample_raw, tmp_path):
        return transform(sample_raw, tmp_path / "clean.csv")

    def test_writes_the_expected_row_count(self, result):
        assert result.rows_in == 8
        assert result.rows_out == EXPECTED_CLEAN_ROWS
        assert result.path.is_file()

    def test_reports_what_was_dropped(self, result):
        assert result.rows_dropped == {
            "missing_date": 0,
            "missing_country": 4,
            "missing_count": 0,
            "negative_count": 2,
            "duplicate_rows": 4,
        }

    def test_output_has_the_documented_columns(self, result):
        assert result.columns == config.OUTPUT_COLUMNS

    def test_output_passes_its_own_validation(self, result):
        frame = pd.read_csv(result.path)
        validate(frame)

    def test_no_negative_counts_survive(self, result):
        frame = pd.read_csv(result.path)
        assert (frame["confirmed"] >= 0).all()

    def test_dates_are_written_in_iso_order(self, result):
        frame = pd.read_csv(result.path)
        assert frame["date"].min() == "2020-01-22"
        assert frame["date"].max() == "2020-01-25"
        assert frame["date"].map(len).eq(10).all()

    def test_expected_countries_survive(self, result):
        frame = pd.read_csv(result.path)
        assert frame["country"].nunique() == EXPECTED_COUNTRIES

    def test_blank_province_becomes_unknown(self, result):
        frame = pd.read_csv(result.path)
        assert not frame["province"].isna().any()
        assert (frame["province"] == "Unknown").any()

    def test_missing_coordinates_are_allowed(self, result):
        frame = pd.read_csv(result.path)
        no_coords = frame[frame["country"] == "NoCoords"]

        assert len(no_coords) == 4
        assert no_coords["latitude"].isna().all()

    def test_duplicate_row_kept_the_later_value(self, result):
        frame = pd.read_csv(result.path)
        springfield = frame[
            (frame["country"] == "Australia") & (frame["date"] == "2020-01-24")
        ]

        assert len(springfield) == 1
        assert springfield["confirmed"].iloc[0] == 3

    def test_rows_are_sorted_by_place_then_date(self, result):
        frame = pd.read_csv(result.path)
        assert frame.equals(
            frame.sort_values(["country", "province", "date"], ignore_index=True)
        )

    def test_negative_rows_are_dropped(self, result):
        frame = pd.read_csv(result.path)
        negative_town = frame[frame["country"] == "Negative-Town"]

        # The two negative days (1/23 and 1/24) are gone, the rest remain.
        assert list(negative_town["date"]) == ["2020-01-22", "2020-01-25"]
        assert list(negative_town["confirmed"]) == [0, 9]

    def test_creates_the_output_directory(self, sample_raw, tmp_path):
        destination = tmp_path / "deep" / "nested" / "clean.csv"
        result = transform(sample_raw, destination)
        assert result.path.is_file()

    def test_reports_the_date_window(self, result):
        assert result.start_date == "2020-01-22"
        assert result.end_date == "2020-01-25"

    def test_is_deterministic(self, sample_raw, tmp_path):
        first = transform(sample_raw, tmp_path / "a.csv")
        second = transform(sample_raw, tmp_path / "b.csv")

        assert (tmp_path / "a.csv").read_text() == (tmp_path / "b.csv").read_text()
        assert first.rows_out == second.rows_out


class TestDateFilter:
    def test_keeps_only_the_requested_window(self, sample_raw, tmp_path):
        result = transform(
            sample_raw,
            tmp_path / "clean.csv",
            start_date="2020-01-23",
            end_date="2020-01-24",
        )
        frame = pd.read_csv(result.path)

        assert set(frame["date"]) == {"2020-01-23", "2020-01-24"}
        assert result.start_date == "2020-01-23"
        assert result.end_date == "2020-01-24"

    def test_end_date_is_inclusive(self, sample_raw, tmp_path):
        result = transform(sample_raw, tmp_path / "clean.csv", end_date="2020-01-23")
        assert result.end_date == "2020-01-23"

    def test_no_filter_keeps_everything(self, sample_raw, tmp_path):
        result = transform(sample_raw, tmp_path / "clean.csv")
        assert result.rows_out == EXPECTED_CLEAN_ROWS
