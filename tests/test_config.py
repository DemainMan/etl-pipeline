"""Tests for src/config.py — the dataset registry and project paths."""

from __future__ import annotations

import pytest

from src import config


class TestRegistry:
    def test_both_datasets_are_registered(self):
        assert set(config.DATASETS) == {"confirmed", "deaths"}

    def test_confirmed_matches_the_original_constants(self):
        # The confirmed dataset must behave exactly as the pipeline did before
        # datasets existed, so nothing that already worked can change.
        spec = config.get_dataset("confirmed")
        assert spec.source_url == config.SOURCE_URL
        assert spec.raw_path == config.DEFAULT_RAW_PATH
        assert spec.processed_path == config.DEFAULT_PROCESSED_PATH
        assert spec.table == config.DEFAULT_TABLE_NAME
        assert spec.output_columns == config.OUTPUT_COLUMNS

    def test_deaths_has_its_own_columns_and_table(self):
        spec = config.get_dataset("deaths")
        assert spec.table == "daily_deaths"
        assert spec.output_columns[-2:] == ["deaths", "new_deaths"]
        assert spec.source_url.endswith("time_series_covid19_deaths_global.csv")

    def test_datasets_never_share_files_or_tables(self):
        specs = list(config.DATASETS.values())
        for attribute in ("source_url", "raw_path", "processed_path", "table"):
            values = [getattr(spec, attribute) for spec in specs]
            assert len(set(values)) == len(values), attribute

    def test_a_dataset_object_is_passed_through(self):
        spec = config.DATASETS["deaths"]
        assert config.get_dataset(spec) is spec

    def test_an_unknown_name_is_rejected_with_the_choices(self):
        with pytest.raises(ValueError, match="confirmed, deaths"):
            config.get_dataset("recovered")

    def test_default_paths_live_inside_the_project(self):
        for spec in config.DATASETS.values():
            assert config.PROJECT_ROOT in spec.raw_path.parents
            assert config.PROJECT_ROOT in spec.processed_path.parents
        assert config.DEFAULT_DB_PATH.parent == config.PROJECT_ROOT
