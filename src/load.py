"""
load.py — Step 3 of the ETL pipeline: LOAD.

Not yet implemented (scaffolding stub).

Planned behaviour:
    Read the cleaned CSV from the Transform step and insert the
    rows into a SQLite database table.

TODO (Day 29-30, Sep 21-22): implement load_to_sqlite()
    - connect to pipeline.db using sqlite3 (stdlib, no install needed)
    - insert rows with an idempotent strategy (delete then insert,
      or INSERT OR IGNORE) so re-running the pipeline is safe
    - commit the transaction and close the connection

Note: sqlite3 ships with Python — no dependency required.
"""
