# BIOS — Business Intelligence Optimization System

BIOS helps enterprises turn business questions into fewer, better, maintainable and governed analytics products.

**Status:** the backend API runs, including the six-agent assistant, governance, lifecycle, approvals and the Power BI Artifact Factory. The Next.js frontend and the optional n8n and Arduino integrations aren't built yet. BIOS generates Power BI project files, but they still need validating in Power BI Desktop.

## Getting started
You need Python 3.11+ on Windows (tested on 3.14). Run these from the repository root:

```powershell
py -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
backend\.venv\Scripts\python.exe -m alembic upgrade head
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Then load the workbook and run the evaluations from a second terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/ingestion/run
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/governance/evaluate
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lifecycle/evaluate
```

API documentation is at <http://127.0.0.1:8000/docs>. To run the tests, use `backend\.venv\Scripts\python.exe -m pytest backend/tests`.

The database is local SQLite by default, and no paid API is needed. The assistant uses a local Ollama model when one is running, and otherwise falls back to its deterministic logic. See [Windows Development Setup](docs/DEVELOPMENT_SETUP.md) and [Local LLM Setup](docs/LOCAL_LLM_SETUP.md).

## Two connected engines
1. **Analytics Optimization Engine:** discover, evaluate, reuse, consolidate, repair, migrate or retire existing analytics.
2. **Analytics Artifact Factory:** create new analytics only when existing assets cannot satisfy the request.

## Locked architecture
- Local Windows development; cloud-ready deployment later.
- Google Antigravity workspace; Claude Code primary implementation agent; Gemini reviewer.
- Next.js + TypeScript + Tailwind CSS + shadcn/ui.
- Python + FastAPI modular monolith.
- SQLite for local development; PostgreSQL optional; pgvector when semantic retrieval is justified.
- Pandas; Pydantic; deterministic Python governance rules.
- Provider-independent AI adapter: local Ollama by default, deterministic fallback, Gemini and Claude not implemented yet.
- Power BI first; n8n for optional workflows; UNO Q optional.
- GitHub as source of truth.

## Repository
`frontend/` UI · `backend/` API and domain logic · `data/` synthetic source workbook and local data · `docs/` specifications · `workflows/` n8n · `hardware/` UNO Q · `tests/` tests.

## Implementation rules
- Reuse before build.
- Never invent KPI definitions, source fields, owners or lineage.
- Preserve source data and provenance.
- AI proposes; deterministic rules validate; authorised humans approve consequential actions.
- Every recommendation explains evidence, uncertainty and next steps.
- Generated artifacts must be reproducible from versioned specifications and controlled templates.
- Core BIOS must work if an LLM provider, n8n or Arduino is unavailable.

## Dataset and data provenance

BIOS uses the Bayer/SinceAI 2026 Builder Data Pack supplied for the SinceAI Hackathon challenge.

The dataset is entirely synthetic and was created by SinceAI, not Bayer. It does not contain Bayer internal operational data, real patient information or confidential business records.

Some product and market names may correspond to publicly known real-world entities. Their inclusion does not imply that the dataset represents actual Bayer business performance.

The dataset is used exclusively as a demonstration and evaluation environment for BIOS. All findings, scores, recommendations and generated reports are based on this synthetic dataset and must not be interpreted as actual Bayer operational results.

