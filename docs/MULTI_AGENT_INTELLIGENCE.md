# BIOS — Milestone 2: Multi-Agent Intelligence & Analytics Discovery Engine

## 1. Overview & Objectives

Milestone 2 implements the multi-agent intelligence layer for BIOS. When a business user submits a natural-language request (e.g. *"I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country"*), BIOS does **not** reflexively generate new Power BI assets. Instead, it systematically investigates existing assets, shared semantic models, canonical KPIs, duplication risks, and governance guardrails to recommend:
- `REUSE`
- `CONSOLIDATE`
- `MODIFY`
- `MIGRATE`
- `BUILD_NEW` (only after all reuse options are exhausted)
- `NEEDS_CLARIFICATION` (when requirements are ambiguous or missing)

---

## 2. Architecture & Specialist Agents

```
backend/app/agents/
├── __init__.py               # Public API exports
├── schemas.py                # Inter-agent contracts & Pydantic response models
├── orchestrator.py           # Central AgentOrchestrator & execution trace recorder
├── execution.py              # Records provider, model and mode for each agent step
├── entity_catalog.py         # Products, markets and KPIs read from the database
├── intent_resolution.py      # Deterministic parser & validation of LLM proposals
├── adapters/                 # Provider-independent LLM layer
│   ├── base.py               # Abstract BaseLLMAdapter & provider error types
│   ├── ollama.py             # Local Ollama adapter (default provider, 0 API keys)
│   ├── deterministic.py      # DeterministicFallbackAdapter (100% reproducible, 0 API keys)
│   ├── claude.py             # Not implemented: raises LLMProviderNotSupportedError
│   ├── gemini.py             # Not implemented: raises LLMProviderNotSupportedError
│   └── factory.py            # Environment-aware adapter factory
└── specialists/              # Six collaborative specialist agents
    ├── llm_assisted.py       # Shared validated LLM step with deterministic fallback
    ├── intent_agent.py       # Specialist 1: Intent Extraction
    ├── discovery_agent.py    # Specialist 2: Catalog Discovery (Exact, Partial, Weak)
    ├── kpi_agent.py          # Specialist 3: KPI Intelligence & Semantic Equivalence
    ├── duplication_agent.py  # Specialist 4: Structural, KPI & Semantic Duplication
    ├── governance_agent.py   # Specialist 5: Governance Guardrails & Milestone 1 Integration
    └── decision_agent.py     # Specialist 6: Decision Synthesis & Action Hierarchy
```

---

## 3. Specialist Agent Responsibilities & Rules

| Agent | Responsibilities | Key Rules & Evidence Sources |
|---|---|---|
| **Intent Agent** | Extracts products, markets, KPIs, dimensions, timeframes, and business purpose. | Never invents unstated requirements; surfaces missing or ambiguous items. |
| **Discovery Agent** | Searches 360 `AnalyticsAssets`, 75 `SemanticModels`, workspaces, and owners. | Classifies into `EXACT`, `PARTIAL`, and `WEAK` tiers with match scores and exact evidence. |
| **KPI Intelligence Agent** | Reconciles requested metrics against 56 KPIs in `KpiCatalog`. | Distinguishes semantic equivalence from similar names; detects 38 unapproved/conflicted KPIs; maps to canonical approved alternatives. |
| **Duplication Agent** | Evaluates potential duplication across candidate assets. | Weighted similarity: Structural (45%), KPI (35%), Title/Semantic (20%). Prioritizes structural/metric evidence over superficial titles. |
| **Governance Agent** | Evaluates governance constraints against Milestone 1 findings and rules. | Identifies hard blockers (unowned assets, unapproved critical KPIs, orphan models) and warnings; mandates human approval. |
| **Decision Agent** | Synthesizes all inputs into an authoritative action recommendation. | Strictly follows hierarchy: REUSE $\rightarrow$ CONSOLIDATE $\rightarrow$ MODIFY $\rightarrow$ MIGRATE $\rightarrow$ BUILD_NEW $\rightarrow$ NEEDS_CLARIFICATION. Never overrides blockers. |

### Local LLM assistance (Milestone 5.5)

The Intent, KPI Intelligence and Decision agents use the local Ollama model where it helps. Discovery, Duplication and Governance never call a model, and the model can't change a decision, blocker or approval. If Ollama is unavailable, the workflow completes deterministically.

Each trace records its provider, model, execution mode, tokens and processor in `execution_metadata_json`. The orchestrator now commits the request and each trace as it finishes, rather than all at the end, so failed runs keep their traces and no write lock is held during inference. See [LOCAL_LLM_SETUP.md](LOCAL_LLM_SETUP.md).

### Normalized intent (Milestone 5.5.1)

The parser reads products, markets and KPIs from the database and sets the baseline. The LLM only proposes additions: it can never add a product or market, and each proposal is validated and recorded with a reason in `intent.resolution`. Every later agent receives the same frozen `BusinessIntent`, so the same intent and database state give the same decision whichever provider is available.

Regions select their catalog markets in discovery. `Europe` stays the requested scope and resolves only through `markets.region`, never through `EMEA`, and any stated geography that isn't fully resolved returns `NEEDS_CLARIFICATION` (Milestone 5.5.2). Governance blockers and warnings are request-specific, and findings on other candidate assets are reported separately as `out_of_scope_warnings`. `GovernanceAgentResult` now rejects unknown fields, and `active_finding_ids` reaches the Decision Agent and the recommendation.

---

## 4. Execution Trace for Official Bayer Challenge Demo

**Submitted Prompt**:
> *"I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."*

### Agent Step Handoffs:
1. **Step 1: IntentAgent** (1.17 ms)
   - Extracted Products: `['Nubeqa']`
   - Extracted Markets: `['Global']`
   - Extracted KPIs: `['revenue growth', 'sales', 'forecast variance', 'market access']`
   - Extracted Dimensions: `['country']`
   - Missing: `['Time horizon or refresh frequency is unspecified']`
2. **Step 2: DiscoveryAgent** (15.73 ms)
   - Searched 360 assets. Discovered 5 exact matches for Nubeqa in Global scope:
     - `AST-0239` (Nubeqa Net Sales Copy, certified, model `SM-062`)
     - `AST-0009` (Nubeqa Supply - US, model `SM-002`)
     - `AST-0062` (Nubeqa Portfolio, model `SM-010`)
3. **Step 3: KpiIntelligenceAgent** (1.51 ms)
   - Matched canonical approved KPIs:
     - Revenue growth $\rightarrow$ `KPI-004` (Net Sales Growth, canonical approved)
     - Sales $\rightarrow$ `KPI-001` (Net Sales, canonical approved)
     - Forecast variance $\rightarrow$ `KPI-042` (Forecast Variance, canonical approved)
     - Market access $\rightarrow$ `KPI-027` (Market Access Coverage, canonical approved)
4. **Step 4: DuplicationAgent** (10.26 ms)
   - Evaluated candidate assets; detected high structural and KPI similarity (0.68) with existing asset `AST-0065`.
5. **Step 5: GovernanceAgent** (5.71 ms)
   - Evaluated active Milestone 1 governance findings on candidate assets; flagged non-canonical KPI usage warning on `AST-0239`.
6. **Step 6: DecisionAgent** (1.03 ms)
   - **Synthesized Decision**: `CONSOLIDATE` (Confidence: 0.88)
   - **Primary Recommendation**: Consolidate requirements into existing duplicate candidate `AST-0065` rather than commissioning new content.
   - **Required Approvals**: Human approval mandated (`approval_required = True`).

---

## 5. API Endpoints

All endpoints are versioned under `/api/v1/assistant`:

- `POST /api/v1/assistant/requests`: Submits a request, executes multi-agent orchestration, persists traces, and returns recommendation.
- `GET /api/v1/assistant/requests`: Lists historical requests with pagination and status filters.
- `GET /api/v1/assistant/requests/{request_id}`: Retrieves original prompt, parsed intent, and request status.
- `GET /api/v1/assistant/requests/{request_id}/recommendation`: Retrieves synthesized decision, confidence, rationale, alternatives, and blockers.
- `GET /api/v1/assistant/requests/{request_id}/trace`: Retrieves full ordered specialist agent execution traces with timing.

---

## 6. Test Suite & Verification

The test suite contains **58 automated tests** executed via `backend\.venv\Scripts\python.exe -m pytest backend/tests`:
- `test_assistant_agents.py` (8 tests): Individual unit tests for Intent, Discovery, KPI Intelligence, Duplication, Governance, and Decision agents.
- `test_assistant_orchestration.py` (2 tests): End-to-end workflow execution, database persistence, and retry on transient failures.
- `test_assistant_api.py` (3 tests): HTTP endpoints (`POST /requests`, `GET /requests`, `GET /trace`, `GET /recommendation`, 404 handlers).
- `test_assistant_demo.py` (1 test): Dedicated validation of the exact Bayer challenge prompt on real dataset.
- Milestone 0 & 1 tests: All 44 existing ingestion, catalog, model, and governance rule tests continue to pass 100%.

