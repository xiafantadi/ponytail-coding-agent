# Current Regression Evidence

Captured on 2026-08-05 from commit `971e7e6` on Windows with Python 3.13.

## Results

| Check | Result |
| --- | --- |
| Full test suite | 603 passed, 3 skipped, 12 warnings |
| Ruff | passed |
| `ponytail` package import | passed |

Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -c "import ponytail"
```

The full test suite completed in 568.78 seconds. The 12 warnings are
`DeprecationWarning` messages for `datetime.utcnow()` in evaluation metrics;
they do not represent failed tests.
