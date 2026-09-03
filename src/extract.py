"""
extract.py — Step 1 of the ETL pipeline: EXTRACT.

Not yet implemented (scaffolding stub).

Planned behaviour:
    Download raw data from a public API or CSV URL, then save it
    to data/raw/ so the Transform step can process it later.

TODO (Day 25, Sep 17): implement extract_from_url(url, output_path)
    - use requests.get() with a timeout
    - call raise_for_status() to catch HTTP errors
    - write the response body to a CSV file under data/raw/
"""
