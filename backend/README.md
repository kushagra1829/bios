FastAPI modular backend. See docs/SYSTEM_ARCHITECTURE.md and AGENTS.md.

## Running the Backend
From the workspace root, using the virtual environment:
```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

## Running Tests
```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests
```

## Endpoints
- `GET /`: Operational status
- `GET /health`: Health diagnostic with UTC timestamp
- `GET /docs`: Swagger UI API documentation
