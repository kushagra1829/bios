# Windows Development Setup

Prerequisites: Git for Windows, Node.js LTS, Python 3.11+ (verify dependency compatibility), PostgreSQL (local or managed dev), Antigravity, Claude Code, and Power BI Desktop for validating artifacts.

1. Create an empty GitHub repository named `bios`.
2. Extract this scaffold and open it in Antigravity.
3. Initialise Git or clone the repository, add the remote and push the scaffold.
4. Read AGENTS.md and docs before coding.
5. Copy `.env.example` to `.env`; never commit it.
6. Place the supplied synthetic builder workbook in `data/source/` locally. This directory is git-ignored.

Backend venv after implementation:
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Frontend after Next.js app is created:
```powershell
cd frontend
npm install
npm run dev
```

First milestone: backend health endpoint, frontend shell, database/migrations, workbook ingestion report and verified source schema. Do not begin AI/Power BI work before data model inspection.
