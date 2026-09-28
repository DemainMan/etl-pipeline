"""
config.py — single source of truth for paths, URLs and column names.

Every other module imports its constants from here, so the pipeline can be
re-pointed at a different dataset by editing this one file.
"""

from pathlib import Path

# --- Paths -----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DEFAULT_RAW_PATH = RAW_DIR / "covid19_confirmed_global.csv"
DEFAULT_PROCESSED_PATH = PROCESSED_DIR / "covid19_confirmed_daily.csv"
DEFAULT_DB_PATH = PROJECT_ROOT / "pipeline.db"

# --- Source ----------------------------------------------------------------

# Johns Hopkins CSSE COVID-19 global time series, confirmed cases.
SOURCE_URL = (
    "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/"
    "csse_covid_19_data/csse_covid_19_time_series/"
    "time_series_covid19_confirmed_global.csv"
)
SOURCE_CITATION = (
    "COVID-19 Data Repository by the Johns Hopkins Center for Health Security "
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

# Used only to give a helpful error message if the upstream file is renamed.
REQUIRED_RAW_COLUMNS = list(RAW_COLUMN_RENAMES)

# Date labels in the raw file look like "1/22/20". Several are tried in order.
RAW_DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d")

# The metric column name used after melting.
METRIC_COLUMN = "confirmed"

# --- Output contract -------------------------------------------------------

# Column order of the processed CSV and of the SQLite table.
OUTPUT_COLUMNS = [
    "date",
    "country",
    "province",
    "latitude",
    "longitude",
    "confirmed",
    "new_cases",
]

# Columns that must never be negative (a "confirmed cases" count).
NON_NEGATIVE_COLUMNS = ["confirmed"]

# Columns that must never be null in the final dataset.
REQUIRED_COLUMNS = ["date", "country", "province", "confirmed"]

# Columns that form the natural key of one row.
KEY_COLUMNS = ["date", "country", "province"]

# Value used when a row has no province (the raw file leaves them blank).
UNKNOWN_PROVINCE = "Unknown"

# --- SQLite ----------------------------------------------------------------

DEFAULT_TABLE_NAME = "daily_cases"
RUNS_TABLE_NAME = "pipeline_runs"

# Date column is stored as TEXT in ISO format (YYYY-MM-DD) so SQLite sorts
# it chronologically without needing a custom collation.
DATE_STORAGE_FORMAT = "%Y-%m-%d"
