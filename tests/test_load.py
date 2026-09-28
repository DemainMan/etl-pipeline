"""Tests for the load step (src/load.py)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from src import config
from src.load import (
    LoadError,
    count_rows,
    create_schema,
    load_to_sqlite,
    summarise,
    validate_table_name,
)


def table_names(db_path: Path) -> list[str]:
    """User-created tables only, ignoring SQLite's internal bookkeeping ones."""
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def columns_of(db_path: Path, table: str) -> list[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def fetch_all(db_path: Path, sql: str) -> list[tuple]:
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute(sql).fetchall()


def row_count(db_path: Path, table: str = "daily_cases") -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        return count_rows(connection, table)


class TestValidateTableName:
    @pytest.mark.parametrize("name", ["daily_cases", "_x", "T1", "a_b_c_9"])
    def test_accepts_plain_identifiers(self, name):
        assert validate_table_name(name) == name

    @pytest.mark.parametrize(
        "name",
        ["", "1abc", "drop table x", "a-b", "a;b", "cases;--", "cases table"],
    )
    def test_rejects_anything_else(self, name):
        with pytest.raises(LoadError, match="Invalid table name"):
            validate_table_name(name)


class TestCreateSchema:
    def test_creates_table_and_indices(self, tmp_path):
        db = tmp_path / "test.db"
        with closing(sqlite3.connect(db)) as connection:
            create_schema(connection, "daily_cases")

        assert table_names(db) == ["daily_cases", config.RUNS_TABLE_NAME]
        assert columns_of(db, "daily_cases") == config.OUTPUT_COLUMNS
        assert "idx_daily_cases_date" in str(fetch_all(db, "SELECT name FROM sqlite_master"))

    def test_is_safe_to_run_twice(self, tmp_path):
        db = tmp_path / "test.db"
        with closing(sqlite3.connect(db)) as connection:
            create_schema(connection, "daily_cases")
            create_schema(connection, "daily_cases")

        assert table_names(db) == ["daily_cases", config.RUNS_TABLE_NAME]

    def test_rejects_a_bad_table_name(self, tmp_path):
        with closing(sqlite3.connect(tmp_path / "test.db")) as connection:
            with pytest.raises(LoadError, match="Invalid table name"):
                create_schema(connection, "bad name; DROP TABLE x")


class TestLoadToSqlite:
    def test_loads_rows_into_the_table(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        result = load_to_sqlite(clean_csv, db)

        assert result.rows_loaded == 4
        assert result.total_rows_in_table == 4
        assert result.table == config.DEFAULT_TABLE_NAME
        assert db.is_file()

    def test_creates_the_schema_on_first_run(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        load_to_sqlite(clean_csv, db)

        assert columns_of(db, "daily_cases") == config.OUTPUT_COLUMNS

    def test_creates_the_database_directory(self, clean_csv, tmp_path):
        db = tmp_path / "nested" / "dir" / "pipeline.db"
        load_to_sqlite(clean_csv, db)
        assert db.is_file()

    def test_uses_a_custom_table_name(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        result = load_to_sqlite(clean_csv, db, table="my_cases")

        assert result.table == "my_cases"
        assert "my_cases" in table_names(db)

    def test_loading_twice_is_idempotent(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"

        first = load_to_sqlite(clean_csv, db)
        second = load_to_sqlite(clean_csv, db)

        assert first.total_rows_in_table == 4
        assert second.rows_loaded == 4
        # The important assertion: no duplicated rows on the second run.
        assert second.total_rows_in_table == 4
        assert row_count(db) == 4

    def test_changed_values_replace_the_old_ones(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        load_to_sqlite(clean_csv, db)

        # Same keys, different counts: the new value must win.
        updated = tmp_path / "updated.csv"
        updated.write_text(
            clean_csv.read_text(encoding="utf-8").replace(",1,1\n", ",7,7\n"),
            encoding="utf-8",
        )
        load_to_sqlite(updated, db)

        rows = fetch_all(
            db,
            "SELECT confirmed, new_cases FROM daily_cases "
            "WHERE country='Australia' ORDER BY date",
        )
        # Both Australia rows survive; only the changed one differs.
        assert rows == [(0, 0), (7, 7)]
        assert row_count(db) == 4

    def test_round_trips_values_without_changing_them(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        load_to_sqlite(clean_csv, db)

        rows = fetch_all(
            db,
            "SELECT date, country, province, latitude, longitude, confirmed, new_cases "
            "FROM daily_cases ORDER BY country, date",
        )
        assert rows == [
            ("2020-01-22", "Albania", "Unknown", 41.15, 20.17, 0, 0),
            ("2020-01-23", "Albania", "Unknown", 41.15, 20.17, 2, 2),
            ("2020-01-22", "Australia", "Springfield", -37.84, 144.99, 0, 0),
            ("2020-01-23", "Australia", "Springfield", -37.84, 144.99, 1, 1),
        ]

    def test_missing_coordinates_are_stored_as_null(self, tmp_path):
        csv = tmp_path / "nulls.csv"
        csv.write_text(
            "date,country,province,latitude,longitude,confirmed,new_cases\n"
            "2020-01-22,NoWhere,Unknown,,,5,5\n",
            encoding="utf-8",
        )
        db = tmp_path / "pipeline.db"
        load_to_sqlite(csv, db)

        assert fetch_all(db, "SELECT latitude, longitude FROM daily_cases") == [(None, None)]

    def test_handles_more_rows_than_one_chunk(self, tmp_path):
        # CHUNK_SIZE is 5,000, so this forces several executemany calls.
        rows = 5_500
        csv = tmp_path / "big.csv"
        csv.write_text(
            "date,country,province,latitude,longitude,confirmed,new_cases\n"
            + "".join(
                f"2020-01-22,Country{i // 100},P{i},1.0,2.0,{i},{i}\n"
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        db = tmp_path / "pipeline.db"
        result = load_to_sqlite(csv, db)

        assert result.rows_loaded == rows
        assert result.total_rows_in_table == rows

    def test_records_the_run_in_the_audit_table(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        result = load_to_sqlite(clean_csv, db)

        runs = fetch_all(
            db,
            "SELECT run_id, rows_loaded, total_rows, status FROM pipeline_runs",
        )
        assert runs == [(result.run_id, 4, 4, "success")]

    def test_audit_table_grows_with_each_run(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        load_to_sqlite(clean_csv, db)
        load_to_sqlite(clean_csv, db)

        assert len(fetch_all(db, "SELECT run_id FROM pipeline_runs")) == 2

    def test_missing_csv_raises(self, tmp_path):
        with pytest.raises(LoadError, match="Run the transform step first"):
            load_to_sqlite(tmp_path / "absent.csv", tmp_path / "pipeline.db")

    def test_csv_with_wrong_columns_raises(self, tmp_path):
        csv = tmp_path / "wrong.csv"
        csv.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

        with pytest.raises(LoadError, match="missing column"):
            load_to_sqlite(csv, tmp_path / "pipeline.db")

    def test_header_only_csv_raises(self, tmp_path):
        csv = tmp_path / "empty.csv"
        csv.write_text(
            "date,country,province,latitude,longitude,confirmed,new_cases\n",
            encoding="utf-8",
        )

        with pytest.raises(LoadError, match="no data rows"):
            load_to_sqlite(csv, tmp_path / "pipeline.db")

    def test_invalid_table_name_raises_before_touching_the_database(
        self, clean_csv, tmp_path
    ):
        db = tmp_path / "pipeline.db"

        with pytest.raises(LoadError, match="Invalid table name"):
            load_to_sqlite(clean_csv, db, table="nope; DROP TABLE daily_cases")

        assert not db.exists()


class TestSummarise:
    def test_describes_a_loaded_table(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        load_to_sqlite(clean_csv, db)

        summary = summarise(db)

        assert "4 rows" in summary
        assert "2 countries" in summary
        assert "2020-01-22 to 2020-01-23" in summary

    def test_reports_a_missing_database(self, tmp_path):
        summary = summarise(tmp_path / "absent.db")
        assert "No database at" in summary

    def test_reports_an_empty_table(self, clean_csv, tmp_path):
        db = tmp_path / "pipeline.db"
        with closing(sqlite3.connect(db)) as connection:
            create_schema(connection, "daily_cases")
            connection.commit()

        assert "is empty" in summarise(db)

    def test_reports_an_unreadable_table(self, tmp_path):
        db = tmp_path / "pipeline.db"
        with closing(sqlite3.connect(db)) as connection:
            create_schema(connection, "daily_cases")
            connection.execute("DROP TABLE daily_cases")
            connection.commit()

        assert "Could not read" in summarise(db)
