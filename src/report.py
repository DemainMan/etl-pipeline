"""
report.py — combined analysis on top of the loaded tables.

Two things live here:

* create_summary_view() joins daily_cases and daily_deaths into one
  `daily_summary` view, adding a case fatality rate (deaths as a percentage
  of confirmed cases). A view stores no data of its own, so it is always in
  step with the tables and re-running the pipeline cannot duplicate it.

* build_report() / write_report() turn the database into a short Markdown
  report: what is loaded, the latest worldwide totals, the ten countries
  with the most cases, data-quality checks and the most recent runs. It is
  meant to be read by a person, so every number is formatted.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import config

__all__ = [
    "ReportError",
    "build_report",
    "create_summary_view",
    "existing_tables",
    "write_report",
]

CASES_TABLE = config.DATASETS["confirmed"].table
DEATHS_TABLE = config.DATASETS["deaths"].table

TOP_N = 10


class ReportError(RuntimeError):
    """Raised when the database cannot be reported on."""


def existing_tables(connection: sqlite3.Connection) -> set[str]:
    """Names of the tables and views currently in the database."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {name for (name,) in rows}


def create_summary_view(db_path: Path | str) -> bool:
    """Create the daily_summary view if both source tables exist.

    Returns True when the view exists afterwards, False when one of the
    tables has not been loaded yet (so there is nothing to join).
    """
    database = Path(db_path)
    if not database.is_file():
        return False

    try:
        with closing(sqlite3.connect(database)) as connection:
            if not {CASES_TABLE, DEATHS_TABLE} <= existing_tables(connection):
                return False
            _create_view(connection)
    except sqlite3.Error as exc:
        raise ReportError(
            f"Could not create the {config.SUMMARY_VIEW_NAME} view: {exc}"
        ) from exc
    return True


def _create_view(connection: sqlite3.Connection) -> None:
    """Join cases and deaths per place and day, with a fatality rate."""
    connection.execute(
        f"""
        CREATE VIEW IF NOT EXISTS {config.SUMMARY_VIEW_NAME} AS
        SELECT c.date,
               c.country,
               c.province,
               c.confirmed,
               c.new_cases,
               d.deaths,
               d.new_deaths,
               CASE WHEN c.confirmed > 0
                    THEN ROUND(100.0 * d.deaths / c.confirmed, 3)
               END AS case_fatality_pct
        FROM {CASES_TABLE} AS c
        JOIN {DEATHS_TABLE} AS d
          ON d.date = c.date
         AND d.country = c.country
         AND d.province = c.province
        """
    )
    connection.commit()


# --- report sections -------------------------------------------------------


def _markdown_table(headers: list[str], rows: list[tuple]) -> list[str]:
    """Render rows as a Markdown table (numbers right-aligned)."""

    def cell(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            return f"{value:,.2f}"
        return str(value)

    def is_number_column(index: int) -> bool:
        values = [row[index] for row in rows if row[index] is not None]
        return bool(values) and all(isinstance(v, int | float) for v in values)

    alignment = ["---:" if is_number_column(i) else "---" for i in range(len(headers))]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(alignment) + "|",
    ]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return lines


def _fatality_pct(deaths: int | None, confirmed: int | None) -> float | None:
    if not confirmed or deaths is None:
        return None
    return 100.0 * deaths / confirmed


def _overview(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    rows = []
    for table in tables:
        count, countries, first, last = connection.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT country), MIN(date), MAX(date) "
            f"FROM {table}"
        ).fetchone()
        rows.append((table, count, countries, first, last))
    return [
        "## What is loaded",
        "",
        *_markdown_table(["Table", "Rows", "Countries", "First date", "Last date"],
                         rows),
        "",
    ]


def _latest_totals(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    """Worldwide cumulative totals on the most recent date."""
    lines = ["## Latest worldwide totals", ""]
    totals: dict[str, tuple[str, int]] = {}
    for name in ("confirmed", "deaths"):
        spec = config.DATASETS[name]
        if spec.table not in tables:
            continue
        date, total = connection.execute(
            f"SELECT date, SUM({spec.metric_column}) FROM {spec.table} "
            f"WHERE date = (SELECT MAX(date) FROM {spec.table})"
        ).fetchone()
        totals[name] = (date, int(total))
        lines.append(f"- **{name.capitalize()}** on {date}: {int(total):,}")

    if len(totals) == 2:
        pct = _fatality_pct(totals["deaths"][1], totals["confirmed"][1])
        lines.append(f"- **Case fatality rate**: {pct:.2f}%")
    lines.append("")
    return lines


def _top_countries(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    """The countries with the most confirmed cases on the latest date."""
    if CASES_TABLE not in tables:
        return []
    has_deaths = DEATHS_TABLE in tables
    if has_deaths:
        rows = connection.execute(
            f"""
            SELECT c.country, SUM(c.confirmed), SUM(d.deaths)
            FROM {CASES_TABLE} AS c
            LEFT JOIN {DEATHS_TABLE} AS d
              ON d.date = c.date AND d.country = c.country
             AND d.province = c.province
            WHERE c.date = (SELECT MAX(date) FROM {CASES_TABLE})
            GROUP BY c.country
            ORDER BY SUM(c.confirmed) DESC, c.country
            LIMIT ?
            """,
            (TOP_N,),
        ).fetchall()
        table_rows = [
            (rank, country, confirmed, deaths, _fatality_pct(deaths, confirmed))
            for rank, (country, confirmed, deaths) in enumerate(rows, start=1)
        ]
        headers = ["#", "Country", "Confirmed", "Deaths", "Fatality %"]
    else:
        rows = connection.execute(
            f"""
            SELECT country, SUM(confirmed)
            FROM {CASES_TABLE}
            WHERE date = (SELECT MAX(date) FROM {CASES_TABLE})
            GROUP BY country
            ORDER BY SUM(confirmed) DESC, country
            LIMIT ?
            """,
            (TOP_N,),
        ).fetchall()
        table_rows = [
            (rank, country, confirmed)
            for rank, (country, confirmed) in enumerate(rows, start=1)
        ]
        headers = ["#", "Country", "Confirmed"]

    return [
        f"## Top {TOP_N} countries by confirmed cases",
        "",
        *_markdown_table(headers, table_rows),
        "",
    ]


def _quality_checks(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    """Re-check the load contract inside the database itself."""
    rows = []
    for name in ("confirmed", "deaths"):
        spec = config.DATASETS[name]
        if spec.table not in tables:
            continue
        keys = ", ".join(config.KEY_COLUMNS)
        checks = {
            "duplicate keys": (
                f"SELECT COUNT(*) FROM (SELECT {keys} FROM {spec.table} "
                f"GROUP BY {keys} HAVING COUNT(*) > 1)"
            ),
            f"negative {spec.metric_column}": (
                f"SELECT COUNT(*) FROM {spec.table} WHERE {spec.metric_column} < 0"
            ),
            "null key values": (
                f"SELECT COUNT(*) FROM {spec.table} WHERE "
                + " OR ".join(f"{k} IS NULL" for k in config.KEY_COLUMNS)
            ),
        }
        for check, sql in checks.items():
            found = int(connection.execute(sql).fetchone()[0])
            rows.append((spec.table, check, found, "PASS" if found == 0 else "FAIL"))
    return [
        "## Data-quality checks",
        "",
        *_markdown_table(["Table", "Check", "Rows found", "Result"], rows),
        "",
    ]


def _recent_runs(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    if config.RUNS_TABLE_NAME not in tables:
        return []
    rows = connection.execute(
        f"SELECT run_id, started_at, source_table, rows_loaded, status "
        f"FROM {config.RUNS_TABLE_NAME} ORDER BY run_id DESC LIMIT 5"
    ).fetchall()
    return [
        "## Recent pipeline runs",
        "",
        *_markdown_table(["Run", "Started (UTC)", "Table", "Rows loaded", "Status"],
                         [(r[0], r[1][:19], r[2], r[3], r[4]) for r in rows]),
        "",
    ]


# --- the whole report ------------------------------------------------------


def build_report(db_path: Path | str) -> str:
    """Return a Markdown report describing the database at `db_path`."""
    database = Path(db_path)
    if not database.is_file():
        raise ReportError(f"No database at {database}. Run the pipeline first.")

    try:
        with closing(sqlite3.connect(database)) as connection:
            present = existing_tables(connection)
            tables = [t for t in (CASES_TABLE, DEATHS_TABLE) if t in present]
            if not tables:
                raise ReportError(
                    f"{database} has no {CASES_TABLE} or {DEATHS_TABLE} table yet."
                )
            sections = [
                _overview(connection, tables),
                _latest_totals(connection, tables),
                _top_countries(connection, tables),
                _quality_checks(connection, tables),
                _recent_runs(connection, sorted(present)),
            ]
    except sqlite3.Error as exc:
        raise ReportError(f"Could not read {database}: {exc}") from exc

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# COVID-19 ETL pipeline report",
        "",
        f"Database: `{database.name}` · generated {generated}",
        "",
        f"Source: {config.SOURCE_CITATION}",
        "",
    ]
    for section in sections:
        lines += section
    return "\n".join(lines).rstrip() + "\n"


def write_report(db_path: Path | str, out_path: Path | str) -> Path:
    """Write build_report() to `out_path` and return the path."""
    destination = Path(out_path)
    text = build_report(db_path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ReportError(
            f"Could not write the report to {destination}: {exc}"
        ) from exc
    return destination
