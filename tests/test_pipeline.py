"""End-to-end tests: run the whole pipeline offline and check the result."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

from src.extract import ExtractError
from src.load import LoadError
from src.run_pipeline import build_parser, main, run_pipeline

from .conftest import EXPECTED_CLEAN_ROWS, EXPECTED_COUNTRIES


@pytest.fixture
def paths(tmp_path) -> dict[str, Path]:
    return {
        "raw": tmp_path / "data" / "raw" / "raw.csv",
        "processed": tmp_path / "data" / "processed" / "clean.csv",
        "db": tmp_path / "pipeline.db",
    }


@pytest.fixture
def run(paths, raw_url):
    """Run the full pipeline against the sample fixture, offline."""
    return run_pipeline(
        source_url=raw_url,
        raw_path=paths["raw"],
        processed_path=paths["processed"],
        db_path=paths["db"],
    )


class TestFullRun:
    def test_produces_all_three_artifacts(self, run, paths):
        assert paths["raw"].is_file()
        assert paths["processed"].is_file()
        assert paths["db"].is_file()

    def test_raw_file_is_a_copy_of_the_source(self, run, paths, sample_raw):
        assert paths["raw"].read_bytes() == sample_raw.read_bytes()

    def test_processed_file_has_the_clean_row_count(self, run, paths):
        assert len(pd.read_csv(paths["processed"])) == EXPECTED_CLEAN_ROWS

    def test_database_has_the_clean_row_count(self, run, paths):
        with closing(sqlite3.connect(paths["db"])) as connection:
            count = connection.execute("SELECT COUNT(*) FROM daily_cases").fetchone()[0]

        assert count == EXPECTED_CLEAN_ROWS

    def test_result_objects_are_returned(self, run):
        assert run.transform_result.rows_out == EXPECTED_CLEAN_ROWS
        assert run.load_result.rows_loaded == EXPECTED_CLEAN_ROWS
        assert run.duration_seconds >= 0

    def test_data_survives_the_round_trip(self, run, paths):
        frame = pd.read_csv(paths["processed"])
        with closing(sqlite3.connect(paths["db"])) as connection:
            stored = pd.read_sql_query("SELECT * FROM daily_cases", connection)

        assert set(frame["country"]) == set(stored["country"])
        assert frame["confirmed"].sum() == stored["confirmed"].sum()

    def test_countries_survive_the_round_trip(self, run, paths):
        with closing(sqlite3.connect(paths["db"])) as connection:
            count = connection.execute(
                "SELECT COUNT(DISTINCT country) FROM daily_cases"
            ).fetchone()[0]

        assert count == EXPECTED_COUNTRIES

    def test_no_negative_counts_are_stored(self, run, paths):
        with closing(sqlite3.connect(paths["db"])) as connection:
            negatives = connection.execute(
                "SELECT COUNT(*) FROM daily_cases WHERE confirmed < 0"
            ).fetchone()[0]

        assert negatives == 0


class TestIdempotency:
    def test_running_twice_gives_the_same_row_count(self, paths, raw_url):
        kwargs = dict(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
        )

        first = run_pipeline(**kwargs)
        second = run_pipeline(**kwargs)

        assert first.load_result.total_rows_in_table == EXPECTED_CLEAN_ROWS
        assert second.load_result.total_rows_in_table == EXPECTED_CLEAN_ROWS

    def test_running_twice_gives_identical_database_contents(self, paths, raw_url):
        kwargs = dict(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
        )
        run_pipeline(**kwargs)
        with closing(sqlite3.connect(paths["db"])) as connection:
            first = connection.execute(
                "SELECT * FROM daily_cases ORDER BY date, country, province"
            ).fetchall()

        run_pipeline(**kwargs)
        with closing(sqlite3.connect(paths["db"])) as connection:
            second = connection.execute(
                "SELECT * FROM daily_cases ORDER BY date, country, province"
            ).fetchall()

        assert first == second

    def test_both_runs_are_recorded_in_the_audit_table(self, paths, raw_url):
        kwargs = dict(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
        )
        run_pipeline(**kwargs)
        run_pipeline(**kwargs)

        with closing(sqlite3.connect(paths["db"])) as connection:
            runs = connection.execute(
                "SELECT status, rows_loaded FROM pipeline_runs ORDER BY run_id"
            ).fetchall()

        assert runs == [("success", EXPECTED_CLEAN_ROWS)] * 2


class TestOptions:
    def test_skip_extract_reuses_the_raw_file(self, paths, raw_url, tmp_path):
        run_pipeline(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
        )

        # Point the source at something that does not exist: if skip_extract
        # really skips the download, this run must still succeed.
        result = run_pipeline(
            source_url=(tmp_path / "gone.csv").as_uri(),
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
            skip_extract=True,
        )

        assert result.load_result.total_rows_in_table == EXPECTED_CLEAN_ROWS

    def test_skip_extract_without_a_raw_file_raises(self, paths, raw_url):
        with pytest.raises(ExtractError, match="does not exist"):
            run_pipeline(
                source_url=raw_url,
                raw_path=paths["raw"],
                processed_path=paths["processed"],
                db_path=paths["db"],
                skip_extract=True,
            )

    def test_date_range_reaches_the_database(self, paths, raw_url):
        run_pipeline(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
            start_date="2020-01-23",
            end_date="2020-01-24",
        )

        with closing(sqlite3.connect(paths["db"])) as connection:
            dates = {
                row[0]
                for row in connection.execute("SELECT DISTINCT date FROM daily_cases")
            }

        assert dates == {"2020-01-23", "2020-01-24"}

    def test_custom_table_name_is_used(self, paths, raw_url):
        result = run_pipeline(
            source_url=raw_url,
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            db_path=paths["db"],
            table="custom_cases",
        )

        assert result.load_result.table == "custom_cases"
        with closing(sqlite3.connect(paths["db"])) as connection:
            names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master")
            }

        assert "custom_cases" in names

    def test_bad_table_name_surfaces_as_a_load_error(self, paths, raw_url):
        with pytest.raises(LoadError, match="Invalid table name"):
            run_pipeline(
                source_url=raw_url,
                raw_path=paths["raw"],
                processed_path=paths["processed"],
                db_path=paths["db"],
                table="bad name",
            )

    def test_unreachable_source_surfaces_as_an_extract_error(self, paths, tmp_path):
        with pytest.raises(ExtractError):
            run_pipeline(
                source_url=(tmp_path / "absent.csv").as_uri(),
                raw_path=paths["raw"],
                processed_path=paths["processed"],
                db_path=paths["db"],
            )


class TestCli:
    def test_main_returns_zero_on_success(self, paths, raw_url, capsys):
        exit_code = main(
            [
                "--source", raw_url,
                "--raw-path", str(paths["raw"]),
                "--processed-path", str(paths["processed"]),
                "--db", str(paths["db"]),
            ]
        )

        assert exit_code == 0
        assert "Pipeline finished" in capsys.readouterr().out

    def test_main_prints_a_summary_of_the_database(self, paths, raw_url, capsys):
        args = [
            "--source", raw_url,
            "--raw-path", str(paths["raw"]),
            "--processed-path", str(paths["processed"]),
            "--db", str(paths["db"]),
        ]
        main(args)

        exit_code = main(["--db", str(paths["db"]), "--summary"])

        assert exit_code == 0
        assert "countries" in capsys.readouterr().out

    def test_main_returns_one_on_failure(self, tmp_path, capsys):
        exit_code = main(
            [
                "--source", "ftp://example.com/data.csv",
                "--raw-path", str(tmp_path / "raw.csv"),
                "--processed-path", str(tmp_path / "clean.csv"),
                "--db", str(tmp_path / "pipeline.db"),
            ]
        )

        assert exit_code == 1

    def test_main_runs_without_network_for_a_file_source(self, paths, raw_url, capsys):
        exit_code = main(
            [
                "--source", raw_url,
                "--raw-path", str(paths["raw"]),
                "--processed-path", str(paths["processed"]),
                "--db", str(paths["db"]),
                "--quiet",
            ]
        )

        assert exit_code == 0
        assert paths["db"].is_file()

    def test_summary_of_a_missing_database_is_reported(self, tmp_path, capsys):
        assert main(["--db", str(tmp_path / "absent.db"), "--summary"]) == 0
        assert "No database at" in capsys.readouterr().out


class TestArgumentParser:
    def test_defaults_point_at_the_project_layout(self):
        args = build_parser().parse_args([])

        assert args.source.startswith("https://")
        assert args.db.endswith("pipeline.db")
        assert args.table == "daily_cases"
        assert args.start_date is None
        assert args.end_date is None
        assert args.skip_extract is False

    def test_date_flags_are_read(self):
        args = build_parser().parse_args(
            ["--start-date", "2020-01-01", "--end-date", "2020-12-31"]
        )

        assert args.start_date == "2020-01-01"
        assert args.end_date == "2020-12-31"

    def test_version_flag_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args(["--version"])

        assert excinfo.value.code == 0
        assert "etl-pipeline" in capsys.readouterr().out
