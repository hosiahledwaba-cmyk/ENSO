# ENSO Shield API

FastAPI service. At Milestone 0 it exposes only `GET /health` (process liveness).
It does **not** produce forecasts, read datasets or connect to a database.

## Local development (Windows PowerShell)

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\uvicorn enso_api.main:app --reload --port 8000
```

## Quality checks

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
.\.venv\Scripts\mypy
```

Configuration is read from `ENSO_*` environment variables. See the root `.env.example`.
