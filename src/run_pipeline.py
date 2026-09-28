"""
run_pipeline.py — orchestrate the full ETL pipeline.

Runs the three steps in order and prints a short report:

    extract  : download the raw CSV        -> data/raw/
    transform: clean and validate it        -> data/processed/
    load     : write it into SQLite        -> pipeline.db

The whole run is idempotent: running it twice produces exactly the same
database contents, because the load step replaces rows on a
(date, country, province) primary key.

Usage
-----
    python -m src.run_pipeline
    python -m src.run_pipeline --start-date 2021-01-01 --end-date 2021-12-31
    python -m src.run_pipeline --skip-extract     # reuse data/raw/ as-is
    python -m src.run_pipeline --source file:///tmp/local.csv
    python -m src.run_pipeline --summary         # just describe the database
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .extract import ExtractError, extract_from_url
from .load import LoadError, load_to_sqlite, summarise
from .transform import TransformError, transform

__all__ = ["PipelineResult", "run_pipeline", "build_parser", "main"]

LOGGER = logging.getLogger(__name__)

VERSION = "1.0.0"


@dataclass(frozen=True)
class PipelineResult:
    """End-to-end outcome, returned so callers (and tests) can assert on it."""

    extract_result: object
    transform_result: object
    load_result: object
    duration_seconds: float

    def __str__(self) -> str:
        return (
            f"extract -> {self.extract_result}; "
            f"transform -> {self.transform_result}; "
            f"load -> {self.load_result}"
        )


def run_pipeline(
    source_url: str = config.SOURCE_URL,
    raw_path: Path | str = config.DEFAULT_RAW_PATH,
    processed_path: Path | str = config.DEFAULT_PROCESSED_PATH,
    db_path: Path | str = config.DEFAULT_DB_PATH,
    table: str = config.DEFAULT_TABLE_NAME,
    start_date: str | None = None,
    end_date: str | None = None,
    timeout: int = config.REQUEST_TIMEOUT_SECONDS,
    skip_extract: bool = False,
) -> PipelineResult:
    """Run extract -> transform -> load and return the combined result."""
    started = time.monotonic()

    LOGGER.info("Step 1/3  EXTRACT    %s", source_url)
    if skip_extract:
        raw = Path(raw_path)
        if not raw.is_file():
            raise ExtractError(
                f"--skip-extract was given but {raw} does not exist. "
                "Run without --skip-extract first."
            )
        LOGGER.info("Skipping download; reusing %s", raw)
        extract_result = raw
    else:
        extract_result = extract_from_url(source_url, raw_path, timeout=timeout)
        LOGGER.info("Saved %s", extract_result)

    LOGGER.info("Step 2/3  TRANSFORM  %s", raw_path)
    transform_result = transform(
        raw_path=raw_path,
        output_path=processed_path,
        start_date=start_date,
        end_date=end_date,
    )
    LOGGER.info(
        "Cleaned %d raw row(s) into %d output row(s) -> %s",
        transform_result.rows_in,
        transform_result.rows_out,
        transform_result.path,
    )

    LOGGER.info("Step 3/3  LOAD       %s", db_path)
    load_result = load_to_sqlite(
        csv_path=processed_path, db_path=db_path, table=table
    )
    LOGGER.info("Wrote %s", load_result)

    return PipelineResult(
        extract_result=extract_result,
        transform_result=transform_result,
        load_result=load_result,
        duration_seconds=time.monotonic() - started,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.run_pipeline",
        description=(
            "Extract, transform and load COVID-19 case data into SQLite. "
            "Safe to re-run: the load step is idempotent."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        default=config.SOURCE_URL,
        help="Source URL (http(s):// or file://).",
    )
    parser.add_argument(
        "--raw-path",
        default=str(config.DEFAULT_RAW_PATH),
        help="Where to save the downloaded raw CSV.",
    )
    parser.add_argument(
        "--processed-path",
        default=str(config.DEFAULT_PROCESSED_PATH),
        help="Where to save the cleaned CSV.",
    )
    parser.add_argument(
        "--db",
        default=str(config.DEFAULT_DB_PATH),
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--table",
        default=config.DEFAULT_TABLE_NAME,
        help="Name of the SQLite table to write.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Only keep rows on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Only keep rows on or before this date (YYYY-MM-DD, inclusive).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.REQUEST_TIMEOUT_SECONDS,
        help="Download timeout in seconds.",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Reuse the existing raw CSV instead of downloading again.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a summary of the database and exit without running anything.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only show warnings and errors.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"etl-pipeline {VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)-8s %(message)s",
        stream=sys.stdout,
    )

    try:
        if args.summary:
            print(summarise(args.db, args.table))
            return 0

        result = run_pipeline(
            source_url=args.source,
            raw_path=args.raw_path,
            processed_path=args.processed_path,
            db_path=args.db,
            table=args.table,
            start_date=args.start_date,
            end_date=args.end_date,
            timeout=args.timeout,
            skip_extract=args.skip_extract,
        )
    except (ExtractError, TransformError, LoadError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.error("Interrupted.")
        return 130

    print()
    print("=" * 62)
    print(f"Pipeline finished in {result.duration_seconds:.2f}s")
    print("=" * 62)
    print(f"  raw       {result.extract_result}")
    print(f"  cleaned   {result.transform_result}")
    print(f"  loaded    {result.load_result}")
    dropped = result.transform_result.rows_dropped
    if any(dropped.values()):
        details = ", ".join(
            f"{reason}={count}" for reason, count in dropped.items() if count
        )
        print(f"  dropped   {details}")
    print()
    print(summarise(args.db, args.table))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
