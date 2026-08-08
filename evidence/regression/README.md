# Current Regression Evidence

Captured on 2026-08-08 from the SWE-bench / resume working tree based on commit
`f91d60b`, on Windows with Python 3.13.

## Results

| Check | Result |
| --- | --- |
| Full test suite | 617 passed, 3 skipped, 12 warnings |
| Ruff | passed |
| `ponytail` package import | passed |

Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -c "import ponytail"
```

The full test suite completed in 440.77 seconds. The 12 warnings are
`DeprecationWarning` messages for `datetime.utcnow()` in evaluation metrics;
they do not represent failed tests.
