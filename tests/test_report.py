"""Tests for the combined analysis (src/report.py): the daily_summary view,
the Markdown report and the `--report` option.

Everything runs offline: the `offline_datasets` fixture (conftest.py) swaps
the registered datasets for copies that point at the two fixtures and at a
temporary directory.

Fixture totals on the last date (2020-01-25), after cleaning:
    confirmed: Albania 10, Negative-Town 9, Australia 5, NoCoords 3,
               Whitespace Land 3, Afghanistan 0              -> 30
    deaths:    1 + 1 + 2 + 1 + 1 + 0                          -> 6
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from src import config
from src.report import (
    ReportError,
    build_report,
    create_summary_view,
    existing_tables,
    write_report,
)
from src.run_pipeline import main, run_all, run_pipeline

from .conftest import EXPECTED_CLEAN_ROWS

# Every confirmed row has a matching deaths row, so the join keeps all 22.
EXPECTED_SUMMARY_ROWS = EXPECTED_CLEAN_ROWS


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "pipeline.db"


@pytest.fixture
def loaded_db(db, offline_datasets) -> Path:
    """A database with both tables loaded and the view created."""
    run_all(db_path=db)
    return db


def query(db_path: Path, sql: str) -> list[tuple]:
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute(sql).fetchall()


class TestSummaryView:
    def test_run_all_loads_both_tables_and_the_view(self, loaded_db):
        with closing(sqlite3.connect(loaded_db)) as connection:
            names = existing_tables(connection)
        assert {"daily_cases", "daily_deaths", "daily_summary"} <= names

    def test_view_joins_every_place_and_day(self, loaded_db):
        [(rows,)] = query(loaded_db, "SELECT COUNT(*) FROM daily_summary")
        assert rows == EXPECTED_SUMMARY_ROWS

    def test_view_columns(self, loaded_db):
        with closing(sqlite3.connect(loaded_db)) as connection:
            cursor = connection.execute("SELECT * FROM daily_summary LIMIT 1")
            columns = [d[0] for d in cursor.description]
        assert columns == [
            "date", "country", "province", "confirmed", "new_cases",
            "deaths", "new_deaths", "case_fatality_pct",
        ]

    def test_case_fatality_rate(self, loaded_db):
        rows = query(
            loaded_db,
            "SELECT case_fatality_pct FROM daily_summary "
            "WHERE country = 'Albania' AND date = '2020-01-25'",
        )
        assert rows == [(10.0,)]

    def test_rate_is_null_when_there_are_no_cases(self, loaded_db):
        rows = query(
            loaded_db,
            "SELECT case_fatality_pct FROM daily_summary "
            "WHERE country = 'Afghanistan'",
        )
        assert rows and all(rate is None for (rate,) in rows)

    def test_creating_the_view_twice_is_harmless(self, loaded_db):
        assert create_summary_view(loaded_db) is True
        assert create_summary_view(loaded_db) is True

    def test_no_view_without_a_database(self, db):
        assert create_summary_view(db) is False
        assert not db.exists()

    def test_no_view_with_only_one_table(self, db, offline_datasets):
        run_pipeline(db_path=db, dataset="confirmed")
        assert create_summary_view(db) is False

    def test_a_single_dataset_run_completes_the_view(self, db, offline_datasets):
        # Loading cases on Monday and deaths on Tuesday still ends with a view.
        assert main(["--db", str(db), "--dataset", "confirmed", "--quiet"]) == 0
        assert main(["--db", str(db), "--dataset", "deaths", "--quiet"]) == 0
        [(rows,)] = query(db, "SELECT COUNT(*) FROM daily_summary")
        assert rows == EXPECTED_SUMMARY_ROWS

    def test_a_corrupt_database_raises_a_report_error(self, db):
        db.write_bytes(b"this is not a sqlite database" * 100)
        with pytest.raises(ReportError, match="Could not create"):
            create_summary_view(db)


class TestBuildReport:
    def test_has_every_section(self, loaded_db):
        report = build_report(loaded_db)
        for heading in (
            "# COVID-19 ETL pipeline report",
            "## What is loaded",
            "## Latest worldwide totals",
            "## Top 10 countries by confirmed cases",
            "## Data-quality checks",
            "## Recent pipeline runs",
        ):
            assert heading in report

    def test_latest_totals_and_rate(self, loaded_db):
        report = build_report(loaded_db)
        assert "**Confirmed** on 2020-01-25: 30" in report
        assert "**Deaths** on 2020-01-25: 6" in report
        assert "**Case fatality rate**: 20.00%" in report

    def test_top_countries_are_ranked(self, loaded_db):
        report = build_report(loaded_db)
        assert "| 1 | Albania | 10 | 1 | 10.00 |" in report
        assert "| 2 | Negative-Town | 9 | 1 | 11.11 |" in report
        # Ties are broken alphabetically, so the order is stable.
        assert report.index("NoCoords") < report.index("Whitespace Land")
        assert "| 6 | Afghanistan | 0 | 0 | - |" in report

    def test_numbers_are_right_aligned(self, loaded_db):
        report = build_report(loaded_db)
        assert "| Table | Rows | Countries | First date | Last date |\n" \
               "|---|---:|---:|---|---|" in report

    def test_quality_checks_pass_on_clean_data(self, loaded_db):
        report = build_report(loaded_db)
        assert report.count("| PASS |") == 6
        assert "FAIL" not in report

    def test_quality_checks_catch_a_bad_row(self, loaded_db):
        with closing(sqlite3.connect(loaded_db)) as connection:
            connection.execute(
                "UPDATE daily_deaths SET deaths = -1 WHERE country = 'Albania'"
            )
            connection.commit()
        report = build_report(loaded_db)
        assert "| daily_deaths | negative deaths | 4 | FAIL |" in report

    def test_recent_runs_are_listed(self, loaded_db):
        report = build_report(loaded_db)
        assert "| 2 |" in report and "daily_deaths" in report
        assert report.count("| success |") == 2

    def test_cases_only_report(self, db, offline_datasets):
        run_pipeline(db_path=db, dataset="confirmed")
        report = build_report(db)

        assert "| # | Country | Confirmed |\n" in report
        assert "Deaths" not in report
        assert "fatality" not in report

    def test_deaths_only_report(self, db, offline_datasets):
        run_pipeline(db_path=db, dataset="deaths")
        report = build_report(db)

        assert "**Deaths** on 2020-01-25: 6" in report
        assert "Top 10" not in report

    def test_missing_database(self, db):
        with pytest.raises(ReportError, match="No database"):
            build_report(db)

    def test_database_without_pipeline_tables(self, db):
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("CREATE TABLE unrelated (x INTEGER)")
        with pytest.raises(ReportError, match="has no daily_cases"):
            build_report(db)

    def test_corrupt_database(self, db):
        db.write_bytes(b"this is not a sqlite database" * 100)
        with pytest.raises(ReportError, match="Could not read"):
            build_report(db)

    def test_report_without_an_audit_table(self, loaded_db):
        with closing(sqlite3.connect(loaded_db)) as connection:
            connection.execute(f"DROP TABLE {config.RUNS_TABLE_NAME}")
        assert "Recent pipeline runs" not in build_report(loaded_db)


class TestWriteReport:
    def test_writes_markdown_and_creates_folders(self, loaded_db, tmp_path):
        out = write_report(loaded_db, tmp_path / "reports" / "report.md")

        assert out.is_file()
        assert out.read_text(encoding="utf-8").startswith("# COVID-19")

    def test_unwritable_destination(self, loaded_db, tmp_path):
        blocker = tmp_path / "a_file"
        blocker.write_text("not a folder")
        with pytest.raises(ReportError, match="Could not write"):
            write_report(loaded_db, blocker / "report.md")


class TestCli:
    def test_dataset_all_with_a_report(self, db, offline_datasets, tmp_path, capsys):
        report = tmp_path / "report.md"
        code = main(["--dataset", "all", "--db", str(db), "--report", str(report)])

        out = capsys.readouterr().out
        assert code == 0
        assert "daily_cases" in out and "daily_deaths" in out
        assert f"Report written to {report}" in out
        assert "Case fatality rate" in report.read_text(encoding="utf-8")

    def test_summary_with_a_report_does_not_run_the_pipeline(
        self, loaded_db, tmp_path, capsys
    ):
        report = tmp_path / "report.md"
        before = query(loaded_db, "SELECT COUNT(*) FROM pipeline_runs")

        code = main(["--db", str(loaded_db), "--summary", "--report", str(report)])

        assert code == 0
        assert report.is_file()
        assert query(loaded_db, "SELECT COUNT(*) FROM pipeline_runs") == before

    def test_report_on_a_missing_database_exits_1(self, tmp_path, caplog):
        with caplog.at_level("ERROR"):
            code = main(["--db", str(tmp_path / "absent.db"), "--summary",
                         "--report", str(tmp_path / "report.md")])

        assert code == 1
        assert "No database" in caplog.text
