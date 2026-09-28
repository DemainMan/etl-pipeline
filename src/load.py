"""
load.py — Step 3 of the ETL pipeline: LOAD.

Reads the cleaned CSV and writes it into a SQLite table.

Idempotency
-----------
Re-running the pipeline must not double the data, so rows are written with
`INSERT OR REPLACE` against a primary key of (date, country, province). A row
that already exists is overwritten with the new value and a genuinely new row
is inserted. Running the pipeline twice therefore leaves the same number of
rows in the table as running it once — this is the behaviour asserted by
tests/test_load.py::test_loading_twice_is_idempotent.

Every run is also appended to a small `pipeline_runs` audit table, which is
handy for answering "when did this data last refresh, and how many rows did it
write?".
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config

__all__ = [
    "LoadError",
    "LoadResult",
    "validate_table_name",
    "create_schema",
    "load_to_sqlite",
    "count_rows",
    "summarise",
]

LOGGER = logging.getLogger(__name__)

# Only plain identifiers are accepted for the table name, because the name is
# interpolated into DDL and cannot be passed as a bound parameter.
_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_COLUMN_TYPES = {
    "date": "TEXT NOT NULL",
    "country": "TEXT NOT NULL",
    "province": "TEXT NOT NULL",
    "latitude": "REAL",
    "longitude": "REAL",
    "confirmed": "INTEGER NOT NULL",
    "new_cases": "INTEGER NOT NULL",
}

# Insert in chunks so a 300k-row file does not build one giant transaction
# in memory all at once.
CHUNK_SIZE = 5_000


class LoadError(RuntimeError):
    """Raised when the cleaned data cannot be written to the database."""


@dataclass(frozen=True)
class LoadResult:
    """What the load step wrote."""

    db_path: Path
    table: str
    rows_loaded: int
    total_rows_in_table: int
    run_id: int
    started_at: datetime
    finished_at: datetime

    def __str__(self) -> str:
        return (
            f"{self.db_path}:{self.table} "
            f"({self.rows_loaded:,} rows written, "
            f"{self.total_rows_in_table:,} total)"
        )


def validate_table_name(name: str) -> str:
    """Reject table names that are not plain SQL identifiers."""
    if not _TABLE_NAME_PATTERN.match(name):
        raise LoadError(
            f"Invalid table name {name!r}. Use letters, digits and "
            "underscores, starting with a letter or underscore."
        )
    return name


def _read_clean_csv(csv_path: Path | str) -> pd.DataFrame:
    """Load the processed CSV, checking it matches the expected contract."""
    path = Path(csv_path)
    if not path.is_file():
        raise LoadError(
            f"Cleaned file not found: {path}. Run the transform step first."
        )

    # A truncated or corrupted file must surface as a LoadError, not as a raw
    # pandas/Unicode exception: the CLI only catches LoadError, so anything
    # else would reach the user as an unhandled traceback.
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise LoadError(f"Cleaned file is empty: {path}") from exc
    except UnicodeDecodeError as exc:
        raise LoadError(f"Cleaned file is not valid UTF-8 text: {path}") from exc
    except pd.errors.ParserError as exc:
        raise LoadError(f"Could not parse cleaned file {path}: {exc}") from exc
    except OSError as exc:
        raise LoadError(f"Could not read cleaned file {path}: {exc}") from exc

    missing = [c for c in config.OUTPUT_COLUMNS if c not in frame.columns]
    if missing:
        raise LoadError(
            f"Cleaned file is missing column(s): {', '.join(missing)}. "
            "It does not look like transform output."
        )
    if frame.empty:
        raise LoadError(f"Cleaned file has no data rows: {path}")

    return frame[config.OUTPUT_COLUMNS]


def create_schema(connection: sqlite3.Connection, table: str) -> None:
    """Create the target table and its indices if they do not exist."""
    table = validate_table_name(table)
    columns = ",\n    ".join(
        f"{name} {_COLUMN_TYPES[name]}" for name in config.OUTPUT_COLUMNS
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            {columns},
            PRIMARY KEY (date, country, province)
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_country ON {table}(country)"
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {config.RUNS_TABLE_NAME} (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            source_table TEXT NOT NULL,
            rows_loaded INTEGER NOT NULL DEFAULT 0,
            total_rows INTEGER,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )


def _insert_rows(
    connection: sqlite3.Connection, table: str, frame: pd.DataFrame
) -> int:
    """Write every row with INSERT OR REPLACE, in chunks."""
    placeholders = ", ".join("?" for _ in config.OUTPUT_COLUMNS)
    columns = ", ".join(config.OUTPUT_COLUMNS)
    statement = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"

    # NaN -> None so SQLite stores a real NULL rather than the text "nan".
    records = frame.astype(object).where(pd.notna(frame), None).to_numpy().tolist()
    written = 0
    for start in range(0, len(records), CHUNK_SIZE):
        chunk = records[start : start + CHUNK_SIZE]
        connection.executemany(statement, chunk)
        written += len(chunk)
    return written


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    """Count the rows currently in `table`."""
    table = validate_table_name(table)
    cursor = connection.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cursor.fetchone()[0])


def load_to_sqlite(
    csv_path: Path | str = config.DEFAULT_PROCESSED_PATH,
    db_path: Path | str = config.DEFAULT_DB_PATH,
    table: str = config.DEFAULT_TABLE_NAME,
) -> LoadResult:
    """Load the cleaned CSV at `csv_path` into `db_path`, idempotently."""
    table = validate_table_name(table)
    frame = _read_clean_csv(csv_path)

    database = Path(db_path)
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LoadError(
            f"Could not create the directory for {database}: {exc}"
        ) from exc

    started_at = datetime.now(timezone.utc)
    LOGGER.info("Loading %d rows into %s", len(frame), database)

    # Connecting is outside the audit-trail try/except below, so an unusable
    # path (read-only directory, missing permissions) is reported as a
    # LoadError here rather than escaping as a raw sqlite3.OperationalError.
    try:
        connection = sqlite3.connect(database)
    except sqlite3.Error as exc:
        raise LoadError(f"Could not open the database at {database}: {exc}") from exc

    with closing(connection):
        run_id = 0
        try:
            create_schema(connection, table)
            cursor = connection.execute(
                f"INSERT INTO {config.RUNS_TABLE_NAME} "
                "(started_at, source_table, rows_loaded, status) "
                "VALUES (?, ?, 0, 'running')",
                (started_at.isoformat(), table),
            )
            run_id = int(cursor.lastrowid or 0)
            # Commit the 'running' row on its own so that a later failure can
            # still be recorded: rolling back the insert would take this row
            # with it and leave no trace of the failed run.
            connection.commit()

            rows_loaded = _insert_rows(connection, table, frame)
            total_rows = count_rows(connection, table)

            finished_at = datetime.now(timezone.utc)
            connection.execute(
                f"UPDATE {config.RUNS_TABLE_NAME} "
                "SET finished_at = ?, rows_loaded = ?, total_rows = ?, "
                "status = 'success', message = NULL WHERE run_id = ?",
                (
                    finished_at.isoformat(),
                    rows_loaded,
                    total_rows,
                    run_id,
                ),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            # Record the failure before giving up, so the audit trail is honest.
            # This UPDATE is best-effort: on a badly corrupted database it can
            # fail too, and that secondary error must not mask the original.
            try:
                connection.execute(
                    f"UPDATE {config.RUNS_TABLE_NAME} "
                    "SET finished_at = ?, status = 'failed', message = ? "
                    "WHERE run_id = ?",
                    (datetime.now(timezone.utc).isoformat(), str(exc), run_id),
                )
                connection.commit()
            except sqlite3.Error:
                LOGGER.warning("Could not record the failed run in the audit table.")
            raise LoadError(f"Failed to load {csv_path} into {database}: {exc}") from exc

    LOGGER.info("Load complete: %d rows written, %d total in %s", rows_loaded, total_rows, table)

    return LoadResult(
        db_path=database,
        table=table,
        rows_loaded=rows_loaded,
        total_rows_in_table=total_rows,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
    )


def summarise(db_path: Path | str, table: str = config.DEFAULT_TABLE_NAME) -> str:
    """Return a short human-readable description of the loaded table."""
    table = validate_table_name(table)
    database = Path(db_path)
    if not database.is_file():
        return f"No database at {database} yet. Run the pipeline first."

    with closing(sqlite3.connect(database)) as connection:
        try:
            total = count_rows(connection, table)
            row = connection.execute(
                f"SELECT MIN(date), MAX(date), COUNT(DISTINCT country) FROM {table}"
            ).fetchone()
        except sqlite3.Error as exc:
            return f"Could not read {database}:{table} ({exc})"

    start, end, countries = row
    if not total:
        return f"{database}:{table} is empty."

    return (
        f"{database}:{table} — {total:,} rows, {countries} countries, "
        f"dates {start} to {end}"
    )
