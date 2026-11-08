from fastapi import APIRouter
from backend.app.api.v1.endpoints.catalog import router as catalog_router
from backend.app.api.v1.endpoints.ingestion import router as ingestion_router
from backend.app.api.v1.endpoints.governance import router as governance_router
from backend.app.api.v1.endpoints.assistant import router as assistant_router
from backend.app.api.v1.endpoints.lifecycle import router as lifecycle_router
from backend.app.api.v1.endpoints.migration import router as migration_router
from backend.app.api.v1.endpoints.approvals import router as approvals_router
from backend.app.api.v1.endpoints.audit import router as audit_router
from backend.app.api.v1.endpoints.integrations import router as integrations_router
from backend.app.api.v1.endpoints.monitoring import router as monitoring_router
from backend.app.api.v1.endpoints.alerts import router as alerts_router
from backend.app.api.v1.endpoints.dashboard import router as dashboard_router
from backend.app.artifacts.router import router as artifacts_router

api_v1_router = APIRouter()

# Mount dashboard telemetry under /api/v1/dashboard
api_v1_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

# Mount catalog endpoints under /api/v1
api_v1_router.include_router(catalog_router, tags=["Catalog"])

# Mount ingestion endpoints under /api/v1/ingestion
api_v1_router.include_router(ingestion_router, prefix="/ingestion", tags=["Ingestion"])

# Mount governance intelligence endpoints under /api/v1/governance
api_v1_router.include_router(governance_router, prefix="/governance", tags=["Governance"])

# Mount multi-agent analytics assistant endpoints under /api/v1/assistant
api_v1_router.include_router(assistant_router, prefix="/assistant", tags=["Assistant"])

# Mount lifecycle optimization endpoints under /api/v1/lifecycle
api_v1_router.include_router(lifecycle_router, prefix="/lifecycle", tags=["Lifecycle"])

# Mount Tableau migration intelligence endpoints under /api/v1/migration
api_v1_router.include_router(migration_router, prefix="/migration", tags=["Migration"])

# Mount human approval workflow endpoints under /api/v1/approvals
api_v1_router.include_router(approvals_router, prefix="/approvals", tags=["Approvals"])

# Mount immutable audit log endpoints under /api/v1/audit
api_v1_router.include_router(audit_router, prefix="/audit", tags=["Audit"])

# Mount BI platform integrations under /api/v1/integrations
api_v1_router.include_router(integrations_router, prefix="/integrations", tags=["Integrations"])

# Mount continuous governance monitoring under /api/v1/monitoring
api_v1_router.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])

# Mount governance alert center under /api/v1/alerts
api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])

# Mount Power BI artifact factory endpoints under /api/v1/artifacts
api_v1_router.include_router(artifacts_router)



