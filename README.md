# etl-pipeline

A simple ETL pipeline that extracts data from a public API/CSV, cleans and transforms it with pandas, and loads it into a SQLite database.

## Goal

Build a small, well-structured ETL pipeline (Extract → Transform → Load) that:

1. Downloads raw data from a public API or CSV URL.
2. Cleans and validates the data with pandas.
3. Loads the cleaned data into a SQLite database for analysis.

The project is a learning portfolio piece, focused on writing clear, beginner-explainable code.

## Status: Scaffolding — pipeline work begins Sep 13

The repo is currently **scaffolded only**. All pipeline modules exist as stubs (docstrings + TODOs) but contain **no working ETL code yet**. The actual pipeline work starts on **Sep 13, 2026** (Phase 6 of the roadmap).

## Planned Architecture

```
CSV / API ──► [extract.py] ──► data/raw/ ──► [transform.py] ──► data/processed/ ──► [load.py] ──► SQLite (pipeline.db)
```

- **Extract**: download raw data and save to `data/raw/`
- **Transform**: read raw CSVs, clean/validate with pandas, save to `data/processed/`
- **Load**: read cleaned CSV, insert rows into a SQLite table (idempotent)

## Folder Map

```
etl-pipeline/
├── data/
│   ├── raw/                    # downloaded raw data (gitignored, .gitkeep kept)
│   └── processed/              # cleaned data output (gitignored, .gitkeep kept)
├── src/
│   ├── extract.py              # Step 1 stub
│   ├── transform.py            # Step 2 stub
│   ├── load.py                 # Step 3 stub
│   └── run_pipeline.py         # orchestration stub
├── test_plan.md                # (future) test plan
├── tests/                      # (future) pytest data-quality tests
├── README.md
├── requirements.txt
└── pipeline.db                 # SQLite database (generated at runtime, gitignored)
```

> Note: `sql_notes/` is also present as a placeholder for future SQL practice.

## Getting Started

```bash
# Clone the repo
git clone https://github.com/DemainMan/etl-pipeline.git
cd etl-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# Install dependencies (pandas, requests)
pip install -r requirements.txt

# sqlite3 ships with Python — no install needed
```

The pipeline cannot be run yet — the modules are scaffolding stubs. Real functionality lands in Phase 6+ (Sep 13 onward).

## Roadmap

See `uploads/qa-and-dataeng-roadmap.md` for the full 32-day plan (Aug 24 – Sep 24, 2026).

| Phase | Dates | Focus |
|-------|-------|-------|
| 6 | Sep 13–16 | SQL & Pandas Fundamentals |
| 7 | Sep 17–20 | Build ETL Pipeline — Extract & Transform |
| 8 | Sep 21–23 | Load & Automate |
| 9 | Sep 24 | Final Polish |

## License

MIT
