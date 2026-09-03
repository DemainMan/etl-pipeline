"""
run_pipeline.py — Orchestrate the full ETL pipeline.

Not yet implemented (scaffolding stub).

Planned behaviour:
    Run the three ETL steps in order:
        1. extract_from_url()  -> downloads raw data to data/raw/
        2. transform()         -> cleans data to data/processed/
        3. load_to_sqlite()    -> inserts clean data into pipeline.db

TODO (Day 31, Sep 23): implement run_pipeline()
    - import extract, transform, load
    - call them in sequence with print() confirmation at each step
    - document that the overall pipeline is idempotent
"""
