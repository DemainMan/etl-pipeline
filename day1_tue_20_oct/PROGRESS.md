# Progress log

Fresh start on Tue 20 Oct 2026. The earlier attempt is kept in git history
under the tag `backup-before-reset-2026-10-20`.

- **Tue 20 Oct 2026 (Day 1)**: Old code removed; scaffold and tooling
  (ruff, pytest-cov with a 100% coverage gate, GitHub Actions on Python
  3.10–3.13). `src/config.py` with a `Dataset` registry for confirmed cases
  and deaths. `src/extract.py`: download with a timeout and HTTP check,
  atomic write, SHA-256, `http(s)://` and `file://`. Two deliberately messy
  fixtures. **28 tests**, 100% coverage.

## Next

- Wed 21 Oct: transform step
- Thu 22 Oct: load step and CLI
- Fri 23 Oct: report, SQL notes, docs, demo, release v1.0.0
