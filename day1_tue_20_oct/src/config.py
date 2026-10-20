"""
config.py — single source of truth for paths, URLs and column names.

Every other module imports its constants from here, so the pipeline can be
re-pointed at a different dataset by editing this one file rather than the
logic.

Two Johns Hopkins series are supported — confirmed cases and deaths. They
share exactly the same wide layout, so each one is described by a small
`Dataset` record (URL, file paths, table, column names) and the same code
handles both.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --- Paths -----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_DB_PATH = PROJECT_ROOT / "pipeline.db"

# --- Source ----------------------------------------------------------------

# Folder of the Johns Hopkins CSSE global time series. The repository stopped
# updating on 2023-03-10, so the data is fixed and results are reproducible.
_SOURCE_BASE = (
    "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/"
    "csse_covid_19_data/csse_covid_19_time_series/"
)
SOURCE_URL = _SOURCE_BASE + "time_series_covid19_confirmed_global.csv"
DEATHS_SOURCE_URL = _SOURCE_BASE + "time_series_covid19_deaths_global.csv"

SOURCE_CITATION = (
    "COVID-19 Data Repository by the Center for Systems Science and "
    "Engineering (CSSE) at Johns Hopkins University "
    "(https://github.com/CSSEGISandData/COVID-19)"
)

REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "etl-pipeline/1.0 (+https://github.com/DemainMan/etl-pipeline)"

# --- Raw input columns -----------------------------------------------------

# Identifier columns that stay as-is when the wide date columns are melted.
RAW_ID_COLUMNS = ["province", "country", "latitude", "longitude"]

# The names used by the raw file, mapped to our clean snake_case names.
RAW_COLUMN_RENAMES = {
    "Province/State": "province",
    "Country/Region": "country",
    "Lat": "latitude",
    "Long": "longitude",
}

# Used to give a helpful error message if the upstream file is renamed.
REQUIRED_RAW_COLUMNS = list(RAW_COLUMN_RENAMES)

# Date labels in the raw file look like "1/22/20". Several are tried in order.
RAW_DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d")

# Dates are stored as ISO text (YYYY-MM-DD) so SQLite sorts them
# chronologically without a custom collation.
DATE_STORAGE_FORMAT = "%Y-%m-%d"

# --- Output contract -------------------------------------------------------

# The default metric (confirmed cases). Other datasets name their own.
METRIC_COLUMN = "confirmed"

# Column order of the confirmed-cases CSV and SQLite table.
OUTPUT_COLUMNS = [
    "date",
    "country",
    "province",
    "latitude",
    "longitude",
    "confirmed",
    "new_cases",
]

# Columns that form the natural key of one row.
KEY_COLUMNS = ["date", "country", "province"]

# Value used when a row has no province (the raw file leaves them blank).
UNKNOWN_PROVINCE = "Unknown"

# --- SQLite ----------------------------------------------------------------

DEFAULT_TABLE_NAME = "daily_cases"
RUNS_TABLE_NAME = "pipeline_runs"

# Joins daily_cases and daily_deaths; created once both have been loaded.
SUMMARY_VIEW_NAME = "daily_summary"

# --- Datasets --------------------------------------------------------------

DEFAULT_RAW_PATH = RAW_DIR / "covid19_confirmed_global.csv"
DEFAULT_PROCESSED_PATH = PROCESSED_DIR / "covid19_confirmed_daily.csv"


@dataclass(frozen=True)
class Dataset:
    """Everything that differs between one source series and another."""

    name: str
    source_url: str
    raw_path: Path
    processed_path: Path
    table: str
    metric_column: str  # the cumulative count, e.g. "confirmed"
    change_column: str  # the day-over-day change, e.g. "new_cases"

    @property
    def output_columns(self) -> list[str]:
        """Column order of this dataset's processed CSV and SQLite table."""
        return [
            "date",
            "country",
            "province",
            "latitude",
            "longitude",
            self.metric_column,
            self.change_column,
        ]


DATASETS: dict[str, Dataset] = {
    "confirmed": Dataset(
        name="confirmed",
        source_url=SOURCE_URL,
        raw_path=DEFAULT_RAW_PATH,
        processed_path=DEFAULT_PROCESSED_PATH,
        table=DEFAULT_TABLE_NAME,
        metric_column=METRIC_COLUMN,
        change_column="new_cases",
    ),
    "deaths": Dataset(
        name="deaths",
        source_url=DEATHS_SOURCE_URL,
        raw_path=RAW_DIR / "covid19_deaths_global.csv",
        processed_path=PROCESSED_DIR / "covid19_deaths_daily.csv",
        table="daily_deaths",
        metric_column="deaths",
        change_column="new_deaths",
    ),
}

DEFAULT_DATASET = "confirmed"


def get_dataset(dataset: str | Dataset) -> Dataset:
    """Return the Dataset for a name such as "deaths" (or pass one through)."""
    if isinstance(dataset, Dataset):
        return dataset
    try:
        return DATASETS[dataset]
    except KeyError:
        known = ", ".join(sorted(DATASETS))
        raise ValueError(
            f"Unknown dataset {dataset!r}. Choose one of: {known}."
        ) from None
