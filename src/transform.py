"""
transform.py — Step 2 of the ETL pipeline: TRANSFORM.

Not yet implemented (scaffolding stub).

Planned behaviour:
    Read the raw CSV(s) saved by the Extract step, clean them up,
    then write the cleaned result to data/processed/.

TODO (Day 26-27, Sep 18-19): implement transform()
    - read raw_data into a pandas DataFrame
    - drop duplicates (drop_duplicates())
    - handle nulls (dropna() / fillna())
    - fix column types (pd.to_datetime(), astype())
    - validate: no negative counts, no missing date/location
    - write cleaned output to data/processed/
"""
