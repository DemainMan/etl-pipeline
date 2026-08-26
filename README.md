# etl-pipeline

A simple ETL pipeline that extracts data from a public API/CSV, cleans and transforms it with pandas, and loads it into a PostgreSQL/SQLite database.

## Status

- **Created**: Aug 24, 2026
- **Pipeline start date**: Sep 13, 2026 (Phase 6 — SQL & Pandas Fundamentals)
- **Current phase**: Repo setup (Aug 24–26)

## Planned Tech Stack

- Python 3.11+
- pandas
- requests
- SQLite / SQLAlchemy
- pytest

## Getting Started

```bash
# Clone the repo
git clone https://github.com/DemainMan/etl-pipeline.git
cd etl-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
```

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
