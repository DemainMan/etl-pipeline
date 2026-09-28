"""
transform.py — Step 2 of the ETL pipeline: TRANSFORM.

Reads the raw wide-format CSV and turns it into a clean, tidy, one-row-per-
day-and-place dataset. The steps are deliberately small and named after what
they do, so the pipeline reads like a checklist:

    read_raw -> rename -> normalise text -> wide_to_long -> parse dates
             -> numeric coercion -> drop invalid rows -> drop duplicates
             -> add new_cases -> validate -> write

The live file ships with two real data quality problems, and the tests in
tests/test_transform.py pin down how each is handled, along with three
defensive rules the source does not currently need:

* province is blank for 198 of 289 rows                -> filled with "Unknown"
* latitude/longitude are blank for 2 rows              -> left as null (not a key)
* negative daily counts are possible if history is     -> those rows are dropped
  revised, though the live file has none
* rows with a blank country are impossible today       -> those rows are dropped
* repeated place/date pairs are impossible today        -> de-duplicated, last wins

The last three are not hypotheticals to be ignored: they are cheap to enforce
and they are what stops a bad source snapshot from quietly loading. The
fixture in tests/fixtures/sample_confirmed.csv contains all of them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import config
from .extract import ExtractError, read_raw_csv

__all__ = [
    "TransformError",
    "ValidationError",
    "TransformResult",
    "read_raw",
    "rename_columns",
    "normalise_text",
    "wide_to_long",
    "parse_dates",
    "coerce_numbers",
    "drop_invalid_rows",
    "drop_duplicates",
    "add_new_cases",
    "validate",
    "transform",
]

LOGGER = logging.getLogger(__name__)


class TransformError(RuntimeError):
    """Raised when the raw file cannot be turned into a clean dataset."""


class ValidationError(TransformError):
    """Raised when the cleaned data still breaks a data-quality rule."""


@dataclass(frozen=True)
class TransformResult:
    """Summary of the transform step, including what was removed and why."""

    path: Path
    rows_in: int
    rows_out: int
    rows_dropped: dict[str, int]
    columns: list[str]
    start_date: str | None
    end_date: str | None

    def __str__(self) -> str:
        return f"{self.path} ({self.rows_out:,} rows)"


# --- individual steps ------------------------------------------------------


def read_raw(raw_path: Path | str) -> pd.DataFrame:
    """Load the raw CSV and check it has the columns we know how to use."""
    try:
        raw = read_raw_csv(raw_path)
    except ExtractError as exc:
        # Re-raise as a TransformError so callers only need to catch one type.
        raise TransformError(str(exc)) from exc

    missing = [c for c in config.REQUIRED_RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise TransformError(
            "Raw file is missing expected column(s): "
            f"{', '.join(missing)}. Found: {', '.join(map(str, raw.columns[:6]))}..."
        )
    if raw.empty:
        raise TransformError(f"Raw file is empty: {raw_path}")
    return raw


def rename_columns(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename the raw headers to snake_case and keep only the known columns."""
    renamed = raw.rename(columns=config.RAW_COLUMN_RENAMES)
    return renamed[config.RAW_ID_COLUMNS + [c for c in renamed.columns
                                           if c not in config.RAW_ID_COLUMNS]]


def normalise_text(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace and replace the blank province with a known value."""
    cleaned = frame.copy()

    for column in ("province", "country"):
        # .astype("string") keeps NaN as NaN rather than turning it into "nan".
        cleaned[column] = cleaned[column].astype("string").str.strip()

    cleaned["province"] = cleaned["province"].fillna(config.UNKNOWN_PROVINCE)
    cleaned["province"] = cleaned["province"].replace("", config.UNKNOWN_PROVINCE)
    return cleaned


def wide_to_long(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn the one-column-per-day layout into one row per day."""
    date_columns = [c for c in frame.columns if c not in config.RAW_ID_COLUMNS]
    if not date_columns:
        raise TransformError("No date columns found in the raw file.")

    long = frame.melt(
        id_vars=config.RAW_ID_COLUMNS,
        value_vars=date_columns,
        var_name="date",
        value_name=config.METRIC_COLUMN,
    )
    LOGGER.debug("Melted %d date columns into %d rows", len(date_columns), len(long))
    return long


def _parse_one_label(label: object) -> datetime | None:
    """Turn a single raw date label such as '1/22/20' into a datetime."""
    if not isinstance(label, str):
        return None
    for fmt in config.RAW_DATE_FORMATS:
        try:
            return datetime.strptime(label, fmt)
        except ValueError:
            continue
    return None


def parse_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert the melted date labels into real datetimes.

    The labels are parsed once per distinct value rather than once per row,
    which keeps this fast even though the melted frame has ~330k rows.
    """
    parsed = frame.copy()
    mapping = {label: _parse_one_label(label) for label in parsed["date"].unique()}
    parsed["date"] = parsed["date"].map(mapping)
    return parsed


def coerce_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    """Make the count and coordinate columns numeric, treating junk as null."""
    coerced = frame.copy()
    for column in (config.METRIC_COLUMN, "latitude", "longitude"):
        coerced[column] = pd.to_numeric(coerced[column], errors="coerce")
    return coerced


def drop_invalid_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop rows that can never be valid, counting each reason separately."""
    working = frame.copy()
    dropped = {
        "missing_date": 0,
        "missing_country": 0,
        "missing_count": 0,
        "negative_count": 0,
    }

    before = len(working)
    working = working[working["date"].notna()]
    dropped["missing_date"] = before - len(working)

    before = len(working)
    working = working[working["country"].notna() & (working["country"] != "")]
    dropped["missing_country"] = before - len(working)

    before = len(working)
    working = working[working[config.METRIC_COLUMN].notna()]
    dropped["missing_count"] = before - len(working)

    before = len(working)
    working = working[working[config.METRIC_COLUMN] >= 0]
    dropped["negative_count"] = before - len(working)

    return working, dropped


def drop_duplicates(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep one row per (date, country, province). Returns the frame and the count."""
    before = len(frame)
    deduped = frame.drop_duplicates(subset=config.KEY_COLUMNS, keep="last")
    return deduped, before - len(deduped)


def add_new_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the day-over-day change in cases for each place.

    This can legitimately be negative, because the source data sometimes
    revises a past day's total downwards. Only `confirmed` is required to be
    non-negative; see validate() below.
    """
    enriched = frame.copy()
    enriched = enriched.sort_values(config.KEY_COLUMNS)
    group_keys = ["country", "province"]
    enriched["new_cases"] = (
        enriched.groupby(group_keys)[config.METRIC_COLUMN].diff().fillna(0).astype("int64")
    )
    return enriched


def validate(frame: pd.DataFrame) -> None:
    """Assert the data-quality rules. Raises ValidationError on any breach."""
    if frame.empty:
        raise ValidationError("Transform produced no rows; nothing to load.")

    for column in config.REQUIRED_COLUMNS:
        if column not in frame.columns:
            raise ValidationError(f"Output is missing the '{column}' column.")
        nulls = int(frame[column].isna().sum())
        if nulls:
            raise ValidationError(
                f"Column '{column}' has {nulls} null value(s); expected none."
            )

    for column in config.NON_NEGATIVE_COLUMNS:
        negatives = int((frame[column] < 0).sum())
        if negatives:
            raise ValidationError(
                f"Column '{column}' has {negatives} negative value(s); expected none."
            )

    duplicates = int(frame.duplicated(subset=config.KEY_COLUMNS).sum())
    if duplicates:
        raise ValidationError(
            f"Found {duplicates} duplicate row(s) for the key "
            f"{', '.join(config.KEY_COLUMNS)}; expected none."
        )



def _format_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Write dates as YYYY-MM-DD so the CSV is stable across locales."""
    formatted = frame.copy()
    formatted["date"] = formatted["date"].dt.strftime(config.DATE_STORAGE_FORMAT)
    return formatted


def _filter_date_range(
    frame: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """Keep only the rows inside the optional [start_date, end_date] window."""
    filtered = frame
    if start_date:
        start = pd.Timestamp(start_date)
        filtered = filtered[filtered["date"] >= start]
    if end_date:
        # end_date is inclusive: bump it to the end of that day.
        end = pd.Timestamp(end_date) + timedelta(days=1)
        filtered = filtered[filtered["date"] < end]
    return filtered


# --- the whole step --------------------------------------------------------


def transform(
    raw_path: Path | str = config.DEFAULT_RAW_PATH,
    output_path: Path | str = config.DEFAULT_PROCESSED_PATH,
    start_date: str | None = None,
    end_date: str | None = None,
) -> TransformResult:
    """Clean the raw CSV at `raw_path` and write the result to `output_path`."""
    destination = Path(output_path)

    raw = read_raw(raw_path)
    rows_in = len(raw)

    working = rename_columns(raw)
    working = normalise_text(working)
    working = wide_to_long(working)
    working = parse_dates(working)
    working = coerce_numbers(working)
    working, dropped = drop_invalid_rows(working)
    working, duplicates = drop_duplicates(working)
    dropped["duplicate_rows"] = duplicates

    working = add_new_cases(working)
    working = _filter_date_range(working, start_date, end_date)

    validate(working)

    # Final column order and sort make the output diff-friendly and the
    # SQLite insert deterministic, which helps the idempotency test.
    output = working[config.OUTPUT_COLUMNS].sort_values(
        ["country", "province", "date"]
    )
    output = _format_dates(output)

    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)

    for reason, count in dropped.items():
        if count:
            LOGGER.info("Dropped %s row(s): %s", f"{count:,}", reason)

    return TransformResult(
        path=destination,
        rows_in=rows_in,
        rows_out=len(output),
        rows_dropped=dropped,
        columns=list(output.columns),
        start_date=output["date"].min() if not output.empty else None,
        end_date=output["date"].max() if not output.empty else None,
    )
