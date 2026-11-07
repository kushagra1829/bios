# BIOS — Official Data Dictionary
## Bayer Pharmaceuticals Builder Data Pack (Since AI 2026)

This document provides a complete, reproducible data dictionary for all 24 worksheets of the official synthetic builder workbook:
`data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx` (Version 2.0).

**Data provenance:** the dataset is entirely synthetic and was created by SinceAI, not Bayer. It contains no Bayer internal operational data, real patient information or confidential business records. Some product and market names may match publicly known real-world entities, but the values don't represent actual Bayer business performance.

---

## Table of Contents
1. [Overview and Estate Topology](#1-overview-and-estate-topology)
2. [Worksheet Summary Matrix](#2-worksheet-summary-matrix)
3. [Core BI & Analytics Metadata Catalog](#3-core-bi--analytics-metadata-catalog)
   - [Workspaces](#workspaces)
   - [Owners](#owners)
   - [Semantic_Models](#semantic_models)
   - [Analytics_Assets](#analytics_assets)
   - [Asset_KPI_Map](#asset_kpi_map)
   - [Asset_Usage](#asset_usage)
   - [Lineage_Edges](#lineage_edges)
4. [Governance & Migration Catalog](#4-governance--migration-catalog)
   - [KPI_Catalog](#kpi_catalog)
   - [Governance_Rules](#governance_rules)
   - [Governance_Signals](#governance_signals)
   - [Migration_Backlog](#migration_backlog)
   - [Data_Quality](#data_quality)
   - [Business_Requests](#business_requests)
5. [Pharma Business Domain Data](#5-pharma-business-domain-data)
   - [Products](#products)
   - [Markets](#markets)
   - [Product_Market_Monthly](#product_market_monthly)
   - [Launch_Milestones](#launch_milestones)
   - [Market_Access](#market_access)
   - [Supply_Operations](#supply_operations)
6. [Reference & Metadata Sheets](#6-reference--metadata-sheets)
   - [START_HERE](#start_here)
   - [Public_References](#public_references)
   - [Data_Dictionary](#data_dictionary)
   - [Package_Overview](#package_overview)
   - [Change_Log](#change_log)

---

## 1. Overview and Estate Topology

- **Scope**: Synthetic prescription-medicine analytics estate modelled on the Bayer Pharmaceuticals context.
- **Divisional Boundary**: Bayer Pharmaceuticals context only. No Crop Science or Consumer Health. The workbook states that it contains no patient-level, HCP-level or personal data.
- **Total Worksheets**: 24
- **Total Data Records**: 8,148 non-empty data records across all 24 sheets (8,151 rows including 3 formatted spacing lines in metadata sheets; physical row sum is 8,175 including headers).
- **Relational Integrity**: 100% of tested foreign keys resolve without orphaned records, with explicit nullable fields where governance rules require them (e.g., 21 unowned assets).

---

## 2. Worksheet Summary Matrix

| # | Sheet Name | Category | Rows | Cols | Candidate Primary Key | Nullable Columns | Duplicate Rows |
|---|------------|----------|------|------|-----------------------|------------------|----------------|
| 1 | `Workspaces` | BI Metadata | 16 | 8 | `workspace_id` | None | 0 |
| 2 | `Owners` | Dimension | 60 | 7 | `owner_id` | None | 0 |
| 3 | `Semantic_Models` | BI Metadata | 75 | 15 | `model_id` | None | 0 |
| 4 | `Analytics_Assets` | Core Asset | 360 | 17 | `asset_id` | `owner_id` (21 / 5.8%) | 0 |
| 5 | `Asset_KPI_Map` | Relational | 1,454 | 4 | `(asset_id, kpi_id)` | None | 0 |
| 6 | `Asset_Usage` | Telemetry | 3,600 | 9 | `(asset_id, month)` | None | 0 |
| 7 | `Lineage_Edges` | Graph | 438 | 5 | `(source_id, target_id)` | None | 0 |
| 8 | `KPI_Catalog` | Governance | 56 | 12 | `kpi_id` | None | 0 |
| 9 | `Governance_Rules` | Governance | 8 | 4 | `rule_id` | None | 0 |
| 10 | `Governance_Signals` | Governance | 410 | 7 | `signal_id` | None | 0 |
| 11 | `Migration_Backlog` | Migration | 94 | 9 | `source_asset_id` | None | 0 |
| 12 | `Data_Quality` | Governance | 147 | 8 | `issue_id` | None | 0 |
| 13 | `Business_Requests` | Request Intake | 150 | 8 | `request_id` | None | 0 |
| 14 | `Products` | Domain Dim | 7 | 7 | `product_id` | None | 0 |
| 15 | `Markets` | Domain Dim | 14 | 7 | `market_id` | None | 0 |
| 16 | `Product_Market_Monthly`| Domain Fact | 980 | 12 | `(product_id, market_id, month)`| `forecast_variance_pct` (110 / 11.2%) | 0 |
| 17 | `Launch_Milestones` | Domain Fact | 35 | 8 | `milestone_id` | None | 0 |
| 18 | `Market_Access` | Domain Fact | 98 | 8 | `(product_id, market_id)` | None | 0 |
| 19 | `Supply_Operations` | Domain Fact | 98 | 9 | `(product_id, market_id)` | None | 0 |
| 20 | `START_HERE` | Documentation | 10 | 8 | Column 1 (Steps/Labels) | Multiple informational | 0 |
| 21 | `Public_References` | Documentation | 6 | 6 | `topic` | None | 0 |
| 22 | `Data_Dictionary` | Documentation | 13 | 5 | `field` | `unit` (10 / 76.9%) | 0 |
| 23 | `Package_Overview` | Documentation | 18 | 8 | Column 1 (Metric Name) | Multiple formatting | 0 |
| 24 | `Change_Log` | Documentation | 1 | 4 | `version` | None | 0 |

---

## 3. Core BI & Analytics Metadata Catalog

### Workspaces
- **Description**: Power BI workspace containers hosting semantic models and reports.
- **Row Count**: 16 | **Cols**: 8
- **Primary Key**: `workspace_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `workspace_id` | `VARCHAR(10)` | 0 (0.0%) | 16 | `WS-001` .. `WS-016` | Unique workspace identifier (PK). |
| `workspace_name` | `VARCHAR(50)` | 0 (0.0%) | 16 | Executive, TA Commercial, Regional | Human-readable name. |
| `scope` | `VARCHAR(20)` | 0 (0.0%) | 2 | `Global` (11, 68.8%), `Regional` (5, 31.3%) | Geographic operational scope. |
| `environment` | `VARCHAR(20)` | 0 (0.0%) | 2 | `Production` (14, 87.5%), `Development` (2, 12.5%) | Deployment lifecycle stage. |
| `platform` | `VARCHAR(20)` | 0 (0.0%) | 1 | `Power BI` (16, 100.0%) | BI server environment. |
| `governance_mode` | `VARCHAR(30)` | 0 (0.0%) | 3 | `managed` (7, 43.8%), `partially_managed` (6, 37.5%), `unmanaged` (3, 18.8%) | Level of IT governance. |
| `classification` | `VARCHAR(20)` | 0 (0.0%) | 2 | `internal` (10, 62.5%), `confidential` (6, 37.5%) | Data privacy tier. |
| `synthetic_record` | `BOOLEAN` | 0 (0.0%) | 1 | `True` (16, 100.0%) | Synthetic flag. |

---

### Owners
- **Description**: Individuals accountable for analytics assets, models, and governed KPIs.
- **Row Count**: 60 | **Cols**: 7
- **Primary Key**: `owner_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `owner_id` | `VARCHAR(10)` | 0 (0.0%) | 60 | `OWN-001` .. `OWN-060` | Unique steward identifier (PK). |
| `owner_name` | `VARCHAR(50)` | 0 (0.0%) | 60 | Synthetic full names | Custodian name. |
| `role` | `VARCHAR(50)` | 0 (0.0%) | 6 | Commercial Lead (16), Medical Lead (14), Market Access Lead (10), Finance Analyst (8), Data Steward (7), Supply Chain Analyst (5) | Organizational function. |
| `scope` | `VARCHAR(30)` | 0 (0.0%) | 6 | Global (22), EMEA (14), North America (10), Asia Pacific (8), Latin America (6) | Operational scope. |
| `status` | `VARCHAR(20)` | 0 (0.0%) | 2 | `active` (49, 81.7%), `inactive` (11, 18.3%) | Employment/stewardship status. |
| `email` | `VARCHAR(60)` | 0 (0.0%) | 60 | synthetic `@synthetic.example` | Email address. |
| `synthetic_record` | `BOOLEAN` | 0 (0.0%) | 1 | `True` (60, 100.0%) | Synthetic flag. |

---

### Semantic_Models
- **Description**: Curated data models serving BI dashboards and natural-language AI agents.
- **Row Count**: 75 | **Cols**: 15
- **Primary Key**: `model_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `model_id` | `VARCHAR(10)` | 0 (0.0%) | 75 | `SM-001` .. `SM-075` | Unique model identifier (PK). |
| `model_name` | `VARCHAR(50)` | 0 (0.0%) | 75 | Distinct business model names | Name of model. |
| `workspace_id` | `VARCHAR(10)` | 0 (0.0%) | 16 | FK -> `Workspaces.workspace_id` | Host workspace container. |
| `product_scope`| `VARCHAR(30)` | 0 (0.0%) | 8 | All Pharma (21), Nubeqa (11), Kerendia (10), Eylea (9), Xarelto (8), Lynkuet (7), Beyonttra (5), Hyrnuo (4) | Target therapeutic asset. |
| `region_scope` | `VARCHAR(30)` | 0 (0.0%) | 5 | Global (28), EMEA (20), North America (14), Asia Pacific (8), Latin America (5) | Geographic scope. |
| `model_type` | `VARCHAR(40)` | 0 (0.0%) | 1 | `Power BI semantic model` (75, 100.0%) | Architecture type. |
| `endorsement` | `VARCHAR(20)` | 0 (0.0%) | 3 | `promoted` (31, 41.3%), `none` (27, 36.0%), `certified` (17, 22.7%) | Trust certification level. |
| `refresh_frequency`| `VARCHAR(20)`| 0 (0.0%) | 3 | `daily` (45, 60.0%), `weekly` (18, 24.0%), `monthly` (12, 16.0%) | Scheduled ETL frequency. |
| `refresh_status` | `VARCHAR(20)` | 0 (0.0%) | 3 | `healthy` (42, 56.0%), `warning` (19, 25.3%), `failed` (14, 18.7%) | Last scheduled execution. |
| `owner_id` | `VARCHAR(10)` | 0 (0.0%) | 42 | FK -> `Owners.owner_id` | Model owner. |
| `table_count` | `INTEGER` | 0 (0.0%) | 17 | Min: 4, Max: 24, Avg: 12.8 | Tables in schema. |
| `measure_count`| `INTEGER` | 0 (0.0%) | 34 | Min: 10, Max: 68, Avg: 34.2 | Formal DAX measures. |
| `ai_readiness` | `VARCHAR(20)` | 0 (0.0%) | 3 | `good` (30, 40.0%), `partial` (24, 32.0%), `poor` (21, 28.0%) | Readiness for AI/NLP. |
| `ai_issue_pattern`|`VARCHAR(30)` | 0 (0.0%) | 4 | `clear` (27, 36.0%), `poor_names` (17, 22.7%), `ambiguous_dates` (16, 21.3%), `implicit_measures` (15, 20.0%) | Known semantics flaw. |
| `synthetic_record`| `BOOLEAN` | 0 (0.0%) | 1 | `True` (75, 100.0%) | Synthetic flag. |

---

### Analytics_Assets
- **Description**: Deployed analytics end-products (reports, workbooks, apps, dashboards).
- **Row Count**: 360 | **Cols**: 17
- **Primary Key**: `asset_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `asset_id` | `VARCHAR(10)` | 0 (0.0%) | 360 | `AST-0001` .. `AST-0360` | Unique asset ID (PK). |
| `asset_name` | `VARCHAR(60)` | 0 (0.0%) | 316 | 40 duplicated names (84 assets) | User-facing report title. |
| `asset_type` | `VARCHAR(20)` | 0 (0.0%) | 4 | `Report` (95), `Workbook` (94), `App` (86), `Dashboard` (85) | Presentation artifact type. |
| `platform` | `VARCHAR(20)` | 0 (0.0%) | 2 | `Power BI` (266, 73.9%), `Tableau` (94, 26.1%) | Source platform. |
| `workspace_id` | `VARCHAR(10)` | 0 (0.0%) | 16 | FK -> `Workspaces.workspace_id` | Container workspace. |
| `model_id` | `VARCHAR(10)` | 0 (0.0%) | 75 | FK -> `Semantic_Models.model_id` | Upstream data model. |
| `product_scope`| `VARCHAR(30)` | 0 (0.0%) | 8 | All Pharma (88), Nubeqa (49), Kerendia (48), Eylea (46), Xarelto (45), Lynkuet (37), Beyonttra (27), Hyrnuo (20) | Brand focus. |
| `market_scope` | `VARCHAR(30)` | 0 (0.0%) | 19 | Global (112), EMEA (78), North America (54), DE (18), US (16), JP (14), etc. | Country or region. |
| `owner_id` | `VARCHAR(10)` | **21 (5.8%)** | 56 | FK -> `Owners.owner_id` (Nullable) | Accountable custodian (**RULE-003**). |
| `created_date` | `DATETIME` | 0 (0.0%) | 321 | Min: 2023-01-15, Max: 2026-08-30 | Initial deployment date. |
| `last_modified`| `DATETIME` | 0 (0.0%) | 284 | Min: 2024-03-01, Max: 2026-09-15 | Last update timestamp. |
| `lifecycle_status`|`VARCHAR(20)`| 0 (0.0%) | 3 | `active` (201, 55.8%), `candidate_retire` (86, 23.9%), `legacy` (73, 20.3%) | Current lifecycle status. |
| `endorsement` | `VARCHAR(20)` | 0 (0.0%) | 3 | `none` (219, 60.8%), `promoted` (91, 25.3%), `certified` (50, 13.9%) | Trust tier. |
| `estimated_audience`|`INTEGER` | 0 (0.0%) | 289 | Min: 12, Max: 1,980, Avg: 624.5 | Monthly active user base. |
| `classification`|`VARCHAR(20)` | 0 (0.0%) | 2 | `internal` (237, 65.8%), `confidential` (123, 34.2%) | Confidentiality tier. |
| `delivery_model`|`VARCHAR(30)`| 0 (0.0%) | 3 | `business_managed` (143, 39.7%), `central_BI` (115, 31.9%), `self_service` (102, 28.3%) | Creation and operating model. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (360, 100.0%) | Synthetic flag. |

---

### Asset_KPI_Map
- **Description**: Explicit many-to-many relationship mapping assets to their calculated metrics.
- **Row Count**: 1,454 | **Cols**: 4
- **Primary Key**: `(asset_id, kpi_id)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `asset_id` | `VARCHAR(10)` | 0 (0.0%) | 360 | FK -> `Analytics_Assets.asset_id` | Target asset. |
| `kpi_id` | `VARCHAR(10)` | 0 (0.0%) | 56 | FK -> `KPI_Catalog.kpi_id` | Referenced metric. |
| `usage_role` | `VARCHAR(20)` | 0 (0.0%) | 3 | `primary` (684, 47.0%), `supporting` (498, 34.3%), `filter` (272, 18.7%) | Role of KPI in visualization. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (1,454, 100.0%) | Synthetic flag. |

---

### Asset_Usage
- **Description**: 10-month historical telemetry and adoption logs for all 360 assets (November 2025 to August 2026).
- **Row Count**: 3,600 | **Cols**: 9
- **Primary Key**: `(asset_id, month)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Min / Max / Distribution | Description & FK |
|-------------|---------------|----------------|----------|--------------------------|------------------|
| `asset_id` | `VARCHAR(10)` | 0 (0.0%) | 360 | FK -> `Analytics_Assets.asset_id` | Target asset. |
| `month` | `VARCHAR(7)` | 0 (0.0%) | 10 | `2025-11` through `2026-08` | Observation month. |
| `views` | `INTEGER` | 0 (0.0%) | 620 | Min: 18, Max: 4,820, Avg: 842.1 | Total monthly view count. |
| `unique_users` | `INTEGER` | 0 (0.0%) | 290 | Min: 8, Max: 1,420, Avg: 215.4 | Unique viewer count. |
| `exports` | `INTEGER` | 0 (0.0%) | 148 | Min: 0, Max: 480, Avg: 41.8 | Excel/CSV export events. |
| `subscriptions`| `INTEGER` | 0 (0.0%) | 86 | Min: 0, Max: 165, Avg: 18.2 | Email digest subscriptions. |
| `avg_load_ms` | `INTEGER` | 0 (0.0%) | 1,450 | Min: 420 ms, Max: 8,950 ms | Average page render time. |
| `query_errors` | `INTEGER` | 0 (0.0%) | 24 | Min: 0, Max: 38, Avg: 4.2 | Visual error count. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (3,600, 100.0%) | Synthetic flag. |

---

### Lineage_Edges
- **Description**: Directed acyclic graph (DAG) edges representing technical and semantic data provenance.
- **Row Count**: 438 | **Cols**: 5
- **Primary Key**: `(source_id, target_id)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `source_id` | `VARCHAR(10)` | 0 (0.0%) | 96 | Upstream model (`SM-xxx`) or asset (`AST-xxx`) | Lineage source node. |
| `target_id` | `VARCHAR(10)` | 0 (0.0%) | 360 | Downstream model (`SM-xxx`) or asset (`AST-xxx`) | Lineage target node. |
| `edge_type` | `VARCHAR(30)` | 0 (0.0%) | 3 | `MODEL_TO_ASSET` (360, 82.2%), `ASSET_TO_ASSET` (56, 12.8%), `MODEL_TO_MODEL` (22, 5.0%) | Edge hierarchy tier. |
| `relationship` | `VARCHAR(50)` | 0 (0.0%) | 3 | `semantic dependency` (360), `embedded / derived` (56), `shared upstream pharma data product` (22) | Semantic dependency definition. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (438, 100.0%) | Synthetic flag. |

---

## 4. Governance & Migration Catalog

### KPI_Catalog
- **Description**: Curated metrics, definitions, domain categories, and approval states.
- **Row Count**: 56 | **Cols**: 12
- **Primary Key**: `kpi_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `kpi_id` | `VARCHAR(10)` | 0 (0.0%) | 56 | `KPI-001` .. `KPI-056` | Unique KPI identifier (PK). |
| `kpi_name` | `VARCHAR(60)` | 0 (0.0%) | 56 | Unique metric title | Descriptive KPI name. |
| `canonical_metric`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (56, 100.0%) | Indicates official metric definition status. |
| `domain` | `VARCHAR(30)` | 0 (0.0%) | 6 | Supply Chain (17), Finance (12), Commercial (10), Market Access (7), BI Governance (6), Launch Excellence (4) | Business domain. |
| `unit` | `VARCHAR(20)` | 0 (0.0%) | 6 | `%` (24), `EUR` (14), `count` (8), `days` (5), `weeks` (3), `index` (2) | Measurement unit. |
| `definition_status`|`VARCHAR(30)`| 0 (0.0%) | 4 | `canonical` (18, 32.1%), `duplicate_candidate` (16, 28.6%), `definition_conflict` (13, 23.2%), `local_variant` (9, 16.1%) | Consistency health state (**RULE-002**). |
| `approval_status`|`VARCHAR(20)`| 0 (0.0%) | 4 | `local` (19, 33.9%), `approved` (18, 32.1%), `unapproved` (11, 19.6%), `draft` (8, 14.3%) | Approval certification level. |
| `default_frequency`|`VARCHAR(20)`|0 (0.0%) | 3 | `monthly` (38), `daily` (12), `quarterly` (6) | Standard refresh cycle. |
| `business_criticality`|`VARCHAR(20)`|0 (0.0%) | 3 | `high` (28, 50.0%), `medium` (20, 35.7%), `critical` (8, 14.3%) | Organizational priority. |
| `owner_id` | `VARCHAR(10)` | 0 (0.0%) | 34 | FK -> `Owners.owner_id` | Steward lead. |
| `description` | `VARCHAR(255)`| 0 (0.0%) | 56 | Technical DAX/business formula text | Business and technical definition. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (56, 100.0%) | Synthetic flag. |

---

### Governance_Rules
- **Description**: The eight core deterministic business rules governing analytics lifecycle decisions.
- **Row Count**: 8 | **Cols**: 4
- **Primary Key**: `rule_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Samples | Description |
|-------------|---------------|----------------|----------|------------------------|-------------|
| `rule_id` | `VARCHAR(10)` | 0 (0.0%) | 8 | `RULE-001` .. `RULE-008` | Primary rule ID. |
| `rule_name` | `VARCHAR(50)` | 0 (0.0%) | 8 | Reuse before build, Canonical KPI first, Owner required, Lineage required, High reach requires trust, Do not migrate waste, AI-ready semantics, Explain every lifecycle action | Formal rule name. |
| `rule_description`|`VARCHAR(255)`|0 (0.0%) | 8 | Full legal specification of rule | Operational standard. |
| `priority` | `VARCHAR(10)` | 0 (0.0%) | 2 | `high` (6, 75.0%), `medium` (2, 25.0%) | Enforcement strictness. |

---

### Governance_Signals
- **Description**: Automated compliance anomalies detected across deployed analytics assets.
- **Row Count**: 410 | **Cols**: 7
- **Primary Key**: `signal_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `signal_id` | `VARCHAR(10)` | 0 (0.0%) | 410 | `SIG-00001` .. `SIG-00410` | Unique signal ID (PK). |
| `asset_id` | `VARCHAR(10)` | 0 (0.0%) | 284 | FK -> `Analytics_Assets.asset_id` | Target asset. |
| `signal_code` | `VARCHAR(30)` | 0 (0.0%) | 5 | `HIGH_REACH_UNENDORSED` (152, 37.1%), `MIGRATION_CANDIDATE` (94, 22.9%), `LIFECYCLE_REVIEW` (86, 21.0%), `SELF_SERVICE_HIGH_REACH` (57, 13.9%), `MISSING_OWNER` (21, 5.1%) | Anomaly categorization. |
| `severity` | `VARCHAR(10)` | 0 (0.0%) | 2 | `medium` (237, 57.8%), `high` (173, 42.2%) | Incident severity. |
| `status` | `VARCHAR(20)` | 0 (0.0%) | 2 | `open` (288, 70.2%), `acknowledged` (122, 29.8%) | Workflow status. |
| `detected_by` | `VARCHAR(30)` | 0 (0.0%) | 3 | `migration_scan` (147, 35.9%), `usage_rule` (138, 33.7%), `metadata_rule` (125, 30.5%) | Audit probe origin. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (410, 100.0%) | Synthetic flag. |

---

### Migration_Backlog
- **Description**: Inventory of legacy Tableau workbooks earmarked for rationalization or Power BI migration.
- **Row Count**: 94 | **Cols**: 9
- **Primary Key**: `source_asset_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `source_asset_id`|`VARCHAR(10)`| 0 (0.0%) | 94 | FK -> `Analytics_Assets.asset_id` | Legacy Tableau asset ID. |
| `product_scope`| `VARCHAR(30)` | 0 (0.0%) | 8 | All Pharma (24), Xarelto (18), Nubeqa (14), Eylea (12), Kerendia (11), Lynkuet (8), Beyonttra (4), Hyrnuo (3) | Product scope. |
| `market_scope` | `VARCHAR(30)` | 0 (0.0%) | 18 | Global (32), EMEA (22), North America (14), etc. | Target market. |
| `recommended_path_candidate`|`VARCHAR(40)`|0 (0.0%)| 5 | `RETIRE` (22, 23.4%), `MIGRATE` (22, 23.4%), `HUMAN_REVIEW` (20, 21.3%), `REBUILD_ON_SHARED_MODEL` (18, 19.1%), `CONSOLIDATE_BEFORE_MIGRATION` (12, 12.8%) | Recommended disposition (**RULE-006**). |
| `candidate_target_model_id`|`VARCHAR(10)`|0 (0.0%)| 48 | FK -> `Semantic_Models.model_id` | Target Power BI model. |
| `complexity` | `VARCHAR(10)` | 0 (0.0%) | 3 | `medium` (38, 40.4%), `high` (31, 33.0%), `low` (25, 26.6%) | Technical conversion difficulty. |
| `status` | `VARCHAR(20)` | 0 (0.0%) | 3 | `assessed` (34, 36.2%), `in_progress` (32, 34.0%), `not_started` (28, 29.8%) | Migration execution state. |
| `synthetic_reason`|`VARCHAR(50)`|0 (0.0%) | 6 | high business criticality (24), shared model available (22), duplicate local logic (18), obsolete low adoption (14), complex custom calculations (10), unverified owner (6) | Rationalization rationale. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (94, 100.0%) | Synthetic flag. |

---

### Data_Quality
- **Description**: 147 audited schema and metadata defects in semantic models and asset records.
- **Row Count**: 147 | **Cols**: 8
- **Primary Key**: `issue_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `issue_id` | `VARCHAR(10)` | 0 (0.0%) | 147 | `DQ-0001` .. `DQ-0147` | Defect record ID (PK). |
| `sheet` | `VARCHAR(30)` | 0 (0.0%) | 2 | `Semantic_Models` (126, 85.7%), `Analytics_Assets` (21, 14.3%) | Target entity table. |
| `record_id` | `VARCHAR(10)` | 0 (0.0%) | 69 | Target `model_id` or `asset_id` | Target record foreign key. |
| `field` | `VARCHAR(30)` | 0 (0.0%) | 4 | `ai_issue_pattern` (48), `ai_readiness` (45), `refresh_status` (33), `owner_id` (21) | Defective field. |
| `issue_value` | `VARCHAR(40)` | 0 (0.0%) | 8 | poor_names, implicit_measures, ambiguous_dates, failed, warning, poor, partial, NULL | Injected invalid value. |
| `severity` | `VARCHAR(10)` | 0 (0.0%) | 3 | `medium` (64, 43.5%), `high` (60, 40.8%), `low` (23, 15.6%) | Audit severity. |
| `impact` | `VARCHAR(100)`| 0 (0.0%) | 4 | Impact description text | Operational consequence. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (147, 100.0%) | Synthetic flag. |

---

### Business_Requests
- **Description**: 150 incoming user requests for new reports, migrations, or KPI inquiries.
- **Row Count**: 150 | **Cols**: 8
- **Primary Key**: `request_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description |
|-------------|---------------|----------------|----------|-----------------------------|-------------|
| `request_id` | `VARCHAR(10)` | 0 (0.0%) | 150 | `REQ-0001` .. `REQ-0150` | Unique request identifier (PK). |
| `request_date` | `DATETIME` | 0 (0.0%) | 69 | Min: 2026-06-01, Max: 2026-09-30 | Date user logged request. |
| `product_context`|`VARCHAR(30)` | 0 (0.0%) | 8 | Lynkuet (24), Beyonttra (23), All Pharma (23), Xarelto (21), Kerendia (19), Hyrnuo (16), Nubeqa (13), Eylea (11) | Extracted brand entity. |
| `market_context` |`VARCHAR(30)` | 0 (0.0%) | 19 | EMEA (32), Global (28), US (18), JP (14), DE (12), FR (10), etc. | Extracted market entity. |
| `request_text` | `VARCHAR(255)`| 0 (0.0%) | 10 | 10 standardized intent prompts (e.g., Tableau Xarelto replacement, Lynkuet launch, Kerendia management) | Natural-language user prompt. |
| `urgency` | `VARCHAR(10)` | 0 (0.0%) | 3 | `normal` (78, 52.0%), `urgent` (41, 27.3%), `high` (31, 20.7%) | User priority. |
| `status` | `VARCHAR(20)` | 0 (0.0%) | 2 | `new` (78, 52.0%), `triaged` (72, 48.0%) | Workflow state. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (150, 100.0%) | Synthetic flag. |

---

## 5. Pharma Business Domain Data

### Products
- **Description**: 7 Bayer Pharmaceuticals prescription medicine brands forming the business scope.
- **Row Count**: 7 | **Cols**: 7
- **Primary Key**: `product_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description |
|-------------|---------------|----------------|----------|-----------------------------|-------------|
| `product_id` | `VARCHAR(10)` | 0 (0.0%) | 7 | `P-NUB`, `P-KER`, `P-EYL`, `P-XAR`, `P-LYN`, `P-BEY`, `P-HYR` | Unique product identifier (PK). |
| `product_name` | `VARCHAR(30)` | 0 (0.0%) | 7 | Nubeqa, Kerendia, Eylea, Xarelto, Lynkuet, Beyonttra, Hyrnuo | Brand commercial title. |
| `therapeutic_area`|`VARCHAR(30)`| 0 (0.0%) | 4 | Cardiovascular (3), Oncology (2), Ophthalmology (1), Women's Health (1) | Therapeutic franchise. |
| `product_type` | `VARCHAR(30)` | 0 (0.0%) | 1 | `Prescription medicine` (7, 100.0%) | Regulatory classification. |
| `portfolio_stage`|`VARCHAR(50)`| 0 (0.0%) | 5 | Established growth product (2), Recent launch (2), Established product / lifecycle (1), Mature / patent-pressure (1), Portfolio expansion (1) | Lifecycle position. |
| `commercial_scope`|`VARCHAR(20)`|0 (0.0%) | 2 | `Global` (4, 57.1%), `Selected markets` (3, 42.9%) | Geographic availability. |
| `public_context_only`|`BOOLEAN`| 0 (0.0%) | 1 | `True` (7, 100.0%) | Governance flag. |

---

### Markets
- **Description**: 14 country-level markets spanning major pharma revenue regions.
- **Row Count**: 14 | **Cols**: 7
- **Primary Key**: `market_id` (`VARCHAR(5)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description |
|-------------|---------------|----------------|----------|-----------------------------|-------------|
| `market_id` | `VARCHAR(5)` | 0 (0.0%) | 14 | DE, FR, IT, ES, FI, SE, UK, US, CA, JP, CN, AU, BR, MX | ISO 2-letter country code (PK). |
| `market_name` | `VARCHAR(30)` | 0 (0.0%) | 14 | Germany, France, Italy, Spain, Finland, Sweden, United Kingdom, USA, Canada, Japan, China, Australia, Brazil, Mexico | Full country name. |
| `region` | `VARCHAR(20)` | 0 (0.0%) | 4 | EMEA (7, 50.0%), Asia Pacific (3, 21.4%), North America (2, 14.3%), Latin America (2, 14.3%) | Geographic reporting region. |
| `currency` | `VARCHAR(5)` | 0 (0.0%) | 10 | EUR (5), USD, CAD, JPY, CNY, AUD, BRL, MXN, SEK, GBP | Local transactional currency. |
| `market_maturity`|`VARCHAR(20)`| 0 (0.0%) | 3 | `mature` (7, 50.0%), `growth` (4, 28.6%), `launch-heavy` (3, 21.4%) | Market dynamics classification. |
| `regulatory_complexity`|`VARCHAR(10)`|0 (0.0%)| 2 | `high` (8, 57.1%), `medium` (6, 42.9%) | Compliance burden. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (14, 100.0%) | Synthetic flag. |

---

### Product_Market_Monthly
- **Description**: Monthly commercial fact data across 7 products and 14 markets (10 months: Nov 2025 – Aug 2026).
- **Row Count**: 980 | **Cols**: 12
- **Primary Key**: `(product_id, market_id, month)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Min / Max / Distribution | Description & FK |
|-------------|---------------|----------------|----------|--------------------------|------------------|
| `product_id` | `VARCHAR(10)` | 0 (0.0%) | 7 | FK -> `Products.product_id` | Foreign key to product. |
| `market_id` | `VARCHAR(5)` | 0 (0.0%) | 14 | FK -> `Markets.market_id` | Foreign key to market. |
| `month` | `VARCHAR(7)` | 0 (0.0%) | 10 | `2025-11` .. `2026-08` | Observation month. |
| `net_sales_m_eur_syn`|`FLOAT` | 0 (0.0%) | 890 | Min: 0.12 M€, Max: 84.50 M€ | Synthetic monthly net sales. |
| `forecast_m_eur_syn`|`FLOAT` | 0 (0.0%) | 884 | Min: 0.15 M€, Max: 82.10 M€ | Synthetic monthly forecast sales. |
| `units_shipped_syn`|`INTEGER` | 0 (0.0%) | 912 | Min: 450, Max: 684,000 units | Total volume units shipped. |
| `forecast_variance_pct`|`FLOAT` | **110 (11.2%)** | 620 | Min: -34.5%, Max: +42.1% | Variance % (Null for launch months). |
| `market_access_coverage_pct_syn`|`FLOAT`|0 (0.0%)| 180 | Min: 12.0%, Max: 100.0% | Reimbursed patient access %. |
| `otif_pct_syn` | `FLOAT` | 0 (0.0%) | 165 | Min: 74.5%, Max: 99.8% | On-Time In-Full delivery %. |
| `inventory_weeks_syn`|`FLOAT` | 0 (0.0%) | 140 | Min: 3.2 weeks, Max: 28.4 weeks | Days of inventory on hand. |
| `value_type` | `VARCHAR(20)` | 0 (0.0%) | 1 | `synthetic_commercial_measure` (980) | Measurement classification. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (980, 100.0%) | Synthetic flag. |

---

### Launch_Milestones
- **Description**: Key commercial and regulatory milestones for recently launched pharmaceuticals.
- **Row Count**: 35 | **Cols**: 8
- **Primary Key**: `milestone_id` (`VARCHAR(10)`)

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `milestone_id` | `VARCHAR(10)` | 0 (0.0%) | 35 | `MLS-001` .. `MLS-035` | Unique milestone ID (PK). |
| `product_id` | `VARCHAR(10)` | 0 (0.0%) | 7 | FK -> `Products.product_id` | Target product. |
| `market_id` | `VARCHAR(5)` | 0 (0.0%) | 14 | FK -> `Markets.market_id` | Target country market. |
| `milestone_type`|`VARCHAR(30)` | 0 (0.0%) | 4 | `Reimbursement Approval` (14), `Commercial Launch` (11), `Regulatory Filing` (6), `First Patient Treatment` (4) | Milestone category. |
| `milestone_date`|`DATETIME` | 0 (0.0%) | 35 | Min: 2025-01-15, Max: 2026-12-15 | Milestone date. |
| `status` | `VARCHAR(20)` | 0 (0.0%) | 3 | `completed` (18, 51.4%), `on_track` (11, 31.4%), `delayed` (6, 17.1%) | Milestone achievement. |
| `business_impact`|`VARCHAR(20)`| 0 (0.0%) | 2 | `critical` (22, 62.9%), `high` (13, 37.1%) | Strategic significance. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (35, 100.0%) | Synthetic flag. |

---

### Market_Access
- **Description**: Country-level reimbursement and coverage access profiles across products.
- **Row Count**: 98 | **Cols**: 8
- **Primary Key**: `(product_id, market_id)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `product_id` | `VARCHAR(10)` | 0 (0.0%) | 7 | FK -> `Products.product_id` | Target product. |
| `market_id` | `VARCHAR(5)` | 0 (0.0%) | 14 | FK -> `Markets.market_id` | Target market. |
| `reimbursement_status`|`VARCHAR(30)`|0 (0.0%)| 4 | `full_coverage` (42), `restricted_coverage` (28), `in_negotiation` (18), `not_covered` (10) | Payer reimbursement state. |
| `coverage_model`|`VARCHAR(30)` | 0 (0.0%) | 3 | `national_formulary` (48), `regional_payer` (32), `private_insurance` (18) | Market payer mechanism. |
| `coverage_pct_syn`|`FLOAT` | 0 (0.0%) | 42 | Min: 0.0%, Max: 100.0% | Eligible population coverage. |
| `trend_status` | `VARCHAR(20)` | 0 (0.0%) | 3 | `stable` (52), `improving` (30), `declining` (16) | Market trend trajectory. |
| `analytics_priority`|`VARCHAR(10)`|0 (0.0%)| 3 | `high` (44), `medium` (36), `low` (18) | Reporting requirement tier. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (98, 100.0%) | Synthetic flag. |

---

### Supply_Operations
- **Description**: Logistics and supply chain reliability profiles across products and destination markets.
- **Row Count**: 98 | **Cols**: 9
- **Primary Key**: `(product_id, market_id)`

| Column Name | Inferred Type | Null Count (%) | Distinct | Valid Values / Distribution | Description & FK |
|-------------|---------------|----------------|----------|-----------------------------|------------------|
| `product_id` | `VARCHAR(10)` | 0 (0.0%) | 7 | FK -> `Products.product_id` | Target product. |
| `market_id` | `VARCHAR(5)` | 0 (0.0%) | 14 | FK -> `Markets.market_id` | Target market. |
| `supply_source` |`VARCHAR(30)` | 0 (0.0%) | 4 | `Leverkusen` (38), `Berlin` (28), `Turku` (20), `Wuppertal` (12) | Bayer manufacturing plant. |
| `primary_mode` |`VARCHAR(20)` | 0 (0.0%) | 3 | `road` (54), `air` (32), `ocean` (12) | Main transport modality. |
| `otif_pct_syn` | `FLOAT` | 0 (0.0%) | 38 | Min: 78.4%, Max: 99.5% | Delivery reliability %. |
| `inventory_weeks_syn`|`FLOAT` | 0 (0.0%) | 35 | Min: 4.1 weeks, Max: 26.2 weeks | Buffer stock level. |
| `forecast_accuracy_pct_syn`|`FLOAT`|0 (0.0%)| 32| Min: 65.0%, Max: 98.2% | Demand forecasting precision. |
| `risk_status` | `VARCHAR(20)` | 0 (0.0%) | 3 | `low` (58), `medium` (28), `high` (12) | Supply bottleneck risk tier. |
| `synthetic_record`|`BOOLEAN` | 0 (0.0%) | 1 | `True` (98, 100.0%) | Synthetic flag. |

---

## 6. Reference & Metadata Sheets

### START_HERE
- **Row Count**: 10 rows | **Cols**: 8
- **Contents**: Operational instructions, critical disclaimers, and 6-step prototype guide.

### Public_References
- **Row Count**: 6 rows | **Cols**: 6
- **Contents**: Official public citations from Bayer Annual Report 2025 justifying domain structures (Prescription medicines, growth drivers Nubeqa & Kerendia).

### Data_Dictionary
- **Row Count**: 13 rows | **Cols**: 5
- **Contents**: Workbook author definitions for 13 specific calculated fields and measures.

### Package_Overview
- **Row Count**: 18 rows | **Cols**: 8
- **Contents**: High-level summary scorecard of the dataset (7 products, 14 markets, 360 assets, 75 models).

### Change_Log
- **Row Count**: 1 row | **Cols**: 4
- **Contents**: Version 2.0 release documentation by Since AI ry (October 8, 2026).

