# BIOS Enterprise Deployment Readiness & Operational Guide

**Milestones:** 5.11 + 5.12  
**Status:** Architecture Ready & Documented  
**Author:** Principal Enterprise Software Architect & DevOps Lead  
**Application Scope:** Software-only Enterprise Business Intelligence Optimization System  

---

## 1. Architecture Overview

```
                      ┌───────────────────────────────┐
                      │    Next.js 14 App Router      │
                      │   (Vercel / Node.js 20+)      │
                      └──────────────┬────────────────┘
                                     │ HTTPS
                                     ▼
                      ┌───────────────────────────────┐
                      │      FastAPI Backend API      │
                      │  (Container / Azure / AWS)    │
                      └──────────────┬────────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           │                         │                         │
           ▼                         ▼                         ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│ Managed PostgreSQL  │   │  Background Worker  │   │ Object Storage      │
│ (Supabase / RDS)    │   │ (Scheduler Thread)  │   │ (S3 / Azure Blob)   │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

> **Operational Disclosure:** Preparing deployment architecture documents does **not** imply that the application is currently deployed to a live production cloud environment. Production deployment requires authorized cloud tenant credentials, managed database provisioning, and identity provider configuration.

---

## 2. Component Deployment Strategies

### 2.1 Frontend (Next.js 14)
- **Target Platform:** Vercel, Netlify, or standalone Node.js Docker container.
- **Node.js Runtime:** Node.js v20 LTS or higher.
- **Configuration:** Set `NEXT_PUBLIC_API_URL` to the publicly routable URL of the FastAPI backend.
- **Rewrites:** For local and unified ingress setups, `next.config.js` routes `/api/v1/:path*` directly to the backend.

### 2.2 Backend API (FastAPI)
- **Target Platform:** Docker container deployed to Azure App Service, AWS App Runner, Google Cloud Run, or Railway.
- **Execution Command:**
  ```bash
  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
  ```
- **Lifespan Initialization:** Table creation and Alembic schema alignment are automatically verified on startup.

### 2.3 Database (PostgreSQL Migration)
- **Engine Support:** SQLAlchemy 2.x models are fully PostgreSQL-compatible.
- **Connection String:**
  ```bash
  DATABASE_URL=postgresql://bios_admin:<SECURE_PASSWORD>@db.example.com:5432/bios_production
  ```
- **Connection Pooling:** In production, use PgBouncer or enable SQLAlchemy connection pool parameters (`pool_size=20`, `max_overflow=10`).

### 2.4 Continuous Governance Worker & Scheduler
- **Development/Small Enterprise:** The background thread scheduler (`monitoring_scheduler.start()`) runs directly within the FastAPI process.
- **Production Scale:** Execute as a standalone background worker container:
  ```bash
  python -m backend.app.monitoring.scheduler
  ```
  Alternatively, trigger jobs via external cron or Azure Logic Apps targeting `POST /api/v1/monitoring/jobs/run`.

---

## 3. Environment Variables Reference

| Variable Name | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite:///data/bios.db` | PostgreSQL or SQLite connection URI |
| `NEXT_PUBLIC_API_URL` | No | `http://127.0.0.1:8000` | Backend API URL for frontend client |
| `POWERBI_TENANT_ID` | Conditional | `""` | Microsoft Entra ID Tenant GUID for Power BI |
| `POWERBI_CLIENT_ID` | Conditional | `""` | Microsoft Entra ID Service Principal Client ID |
| `POWERBI_CLIENT_SECRET` | Conditional | `""` | Service Principal Client Secret (Store in Secret Manager) |
| `POWERBI_WORKSPACE_FILTER` | No | `""` | Optional substring filter for Power BI workspace sync |
| `TABLEAU_SERVER_URL` | Conditional | `""` | Tableau Server / Cloud base URL |
| `TABLEAU_SITE_NAME` | Conditional | `""` | Tableau Cloud / Server content site identifier |
| `TABLEAU_PAT_NAME` | Conditional | `""` | Tableau Personal Access Token Name |
| `TABLEAU_PAT_SECRET` | Conditional | `""` | Tableau Personal Access Token Secret |
| `OLLAMA_BASE_URL` | No | `http://127.0.0.1:11434` | Ollama inference API endpoint |
| `OLLAMA_MODEL` | No | `qwen2.5:3b` | Primary SLM model for intelligence agents |

---

## 4. Security & Hardening Checklist

- [ ] All external API credentials stored in Azure Key Vault, AWS Secrets Manager, or Doppler.
- [ ] CORS origins in `backend/app/main.py` locked down to authorized production domain(s).
- [ ] Database SSL mode enabled (`sslmode=require`).
- [ ] Invariant N4 live owner authority preserved for destructive lifecycle actions.
- [ ] Invariant N5 synchronous waiver expiry maintained in continuous re-evaluation.
- [ ] Invariant N6 RULE-008 verified explanation required for automated interventions.
- [ ] Strict 404 response enforced for `/arduino` route.

