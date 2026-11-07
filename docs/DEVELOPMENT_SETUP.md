# Windows Development Setup

**Prerequisites:** Git for Windows and Python 3.11+ (tested on 3.14).

**Optional:**
- [Ollama](LOCAL_LLM_SETUP.md), for LLM-assisted agents
- Power BI Desktop, for validating generated artifacts
- PostgreSQL, instead of the default SQLite
- Node.js LTS, once the frontend exists

Read AGENTS.md and the docs before coding. Run every command below from the repository root.

## 1. Install the backend

```powershell
git clone https://github.com/kushagra1829/bios.git
cd bios
py -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Never commit `.env`.

## 2. Create the database

```powershell
backend\.venv\Scripts\python.exe -m alembic upgrade head
```

This creates a local SQLite database at `data/bios.db`, which git ignores.

## 3. Start the API

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Add `--reload` to restart automatically when code changes.

## 4. Load the data

The synthetic workbook is in the repository at `data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx`. With the API running, load it and run the evaluations from a second terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/ingestion/run
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/governance/evaluate
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lifecycle/evaluate
```

API documentation is at <http://127.0.0.1:8000/docs>.

## 5. Run the tests

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests
```

The tests need the data from step 4, and they add run records to your local database. Live model tests are separate; see [LOCAL_LLM_SETUP.md](LOCAL_LLM_SETUP.md).

## Optional: use PostgreSQL

SQLite needs no setup. To use PostgreSQL instead, install its driver and set `DATABASE_URL` in `.env` before step 2:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-postgres.txt
```

```text
DATABASE_URL=postgresql+psycopg://bios:your-password@localhost:5432/bios
```

BIOS is developed and tested on SQLite. The test suite hasn't been run against a PostgreSQL server.

## Frontend

The Next.js frontend hasn't been created yet, so `frontend/` contains only placeholders.
