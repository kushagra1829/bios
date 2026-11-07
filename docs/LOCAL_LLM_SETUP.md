# Local LLM setup (Ollama)

BIOS runs its six agents against a local model through Ollama. No API key or paid service is needed. If Ollama is unavailable, BIOS still completes every request using its deterministic logic and records the reason on each trace.

## Quick start

Run these from the repository root in PowerShell.

1. Install Ollama from <https://ollama.com/download>, then install the model:

   ```powershell
   ollama pull qwen3.5:4b
   ```

2. Apply the database migration. It adds the nullable `agent_execution_traces.execution_metadata_json` column, and the assistant fails with a missing-column error until it is applied:

   ```powershell
   backend\.venv\Scripts\python.exe -m alembic upgrade head
   ```

3. Run the demonstration:

   ```powershell
   backend\.venv\Scripts\python.exe backend/scripts/demo_local_llm.py
   ```

   To try your own request, add it as an argument in quotes.

The demo never simulates a model call. It exits with code 2 if Ollama can't serve, and with code 1 if fewer than two agents completed a real LLM-assisted run.

## Configuration

All settings are optional environment variables, and `.env.example` lists them. If you already have a `.env`, add only the lines you want to change.

| Variable | Default | Purpose |
|---|---|---|
| `BIOS_LLM_PROVIDER` | `ollama` | `ollama`, `gemini`, `claude` or `deterministic` (not case-sensitive) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service address |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Model name, exactly as `ollama list` shows it |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Limit for one `/api/chat` request |
| `OLLAMA_MAX_RETRIES` | `1` | Extra attempts after invalid output or an HTTP 5xx |
| `OLLAMA_NUM_CTX` | `8192` | Context window in tokens |
| `OLLAMA_KEEP_ALIVE` | `10m` | How long the model stays loaded after a call |

`gemini` and `claude` are selectable, but neither is implemented. Setting an API key changes nothing: the adapters raise `LLMProviderNotSupportedError` if called directly and return no content. When one is selected, BIOS uses its deterministic logic, and traces record `DETERMINISTIC_FALLBACK` with provider `deterministic_fallback` and the reason.

## How the agents use the model

Agents run one at a time, and each run loads one model.

| Agent | Mode | What the model may do | What stays deterministic |
|---|---|---|---|
| Intent | LLM-assisted | Map paraphrased metrics to approved KPIs, add stated dimensions and time periods, and write the business purpose | Products and markets come only from the catalog-driven parser. Each proposal is validated and recorded. Missing items and confidence are recalculated by rule. |
| Discovery | Deterministic | Nothing | Catalog queries and match tiers |
| KPI Intelligence | LLM-assisted | Add an advisory review of non-exact matches in `llm_review` | KPI IDs, approval status and conflict flags |
| Duplication | Deterministic | Nothing | Weighted similarity scoring |
| Governance | Deterministic | Nothing | Blockers, warnings and rule evaluation |
| Decision | LLM-assisted | Write the advisory `llm_narrative` after the decision is made | Decision, confidence, rationale, blockers and human approval |

The Decision Agent rejects a narrative if it contradicts the decision, the approval requirement or the blocker count, or if it cites an ID that isn't in the decision's facts. The decision still stands, and the narrative is left empty.

## How a request becomes one intent

1. **The original request is kept verbatim** in `raw_prompt`.
2. **The deterministic parser sets the baseline** from the `products`, `markets` and `kpi_catalog` tables.
3. **The LLM proposes additions.** Nothing it returns is used directly.
4. **Each proposal is validated** and recorded with a reason:

   | Proposal | Accepted only when |
   |---|---|
   | Product or market | Never added. It can only confirm a baseline value, so the LLM can't change which assets a request looks at. |
   | KPI | The phrase is stated in the request and isn't part of a longer KPI the parser already matched, the target is an approved canonical KPI, and they share a specific word |
   | Stated metric with no KPI | Never added. It's listed in `unresolved_terms` for a person to review. |
   | Dimension | It's stated in the request and isn't a product, market or KPI |
   | Time period | It's stated in the request and is a real time expression |
   | Business purpose | It adds no product, market or KPI beyond the intent. It's descriptive and doesn't affect decisions. |

5. **One frozen `BusinessIntent` goes to every later agent.** The same intent and database state give the same decision, whichever provider is available.

The audit record is stored in `intent.resolution`, inside `assistant_requests.parsed_intent_json`:

| Field | Contents |
|---|---|
| `original_request` | The request as written |
| `deterministic_intent` | The parser's baseline |
| `llm_proposal` | The model's raw proposal, or null if none |
| `accepted` | Proposals added to the intent, each with a reason |
| `confirmed` | Proposals the baseline already had |
| `rejected` | Proposals not used, each with a reason |

### Recognising geography

Two-letter market codes need evidence, because some are also English words:

| Written as | Result |
|---|---|
| `United States`, `Finland`, `EMEA`, `global` | Accepted in any case |
| `FI`, `DE` (uppercase) | Accepted |
| `fi`, `de` (lowercase) | Accepted only with geographic context, such as `in fi` or `fi market` |
| `Sales in the US`, `US market`, `Compare FI and US` | Accepted |
| `Show us the sales`, `Build a dashboard for us` | Not a market |
| `Sales in us`, `Show US the sales` | Not resolved, and reported as ambiguous |
| `IT budget dashboard` | Not resolved, and reported as ambiguous (Italy or Information Technology) |
| `Sales in IT`, `IT market`, `IT and DE` | Accepted as Italy |
| `in America` | Not resolved, and reported as ambiguous (`US` or `North America`) |
| `Europe` | Kept as the requested scope and resolved per market (see below) |
| `by country` | A dimension only. It doesn't imply any market. |

The workbook has no alias table, so the aliases in [entity_catalog.py](../backend/app/agents/entity_catalog.py) are BIOS terminology, such as `USA` and `APAC`. Each works only while its target exists in the database.

### Geography resolution record

`intent.geography` keeps the request's geography separate from the markets it resolved to:

| Field | Contents |
|---|---|
| `status` | `RESOLVED`, `PARTIALLY_RESOLVED`, `NEEDS_CLARIFICATION` or `NOT_SPECIFIED` |
| `phrases[].original_phrase` | The geography as the user wrote it |
| `phrases[].normalized_scope` | The scope it means, such as `Europe`, `EMEA` or `FI` |
| `phrases[].resolved_market_ids` | Markets it resolved to |
| `phrases[].suggested_market_ids` | Unverified suggestions that need the user's confirmation. They're never used as matches. |
| `phrases[].catalog_evidence` | What the catalog actually records |
| `phrases[].external_context` | General knowledge the catalog doesn't record, labelled as such |
| `resolved_market_ids` | All resolved values, including asset scopes such as `Global` |
| `unresolved_geography` | Phrases not fully resolved |
| `explanation` | Why, in plain language |

`intent.markets` is what later agents search on, and it holds resolved values only.

### Europe

`Europe` is never converted to `EMEA`. A market counts as European only if its own `markets.region` value says so:

| What `markets.region` records | Geography status | Effect |
|---|---|---|
| Every related market is classified as European | `RESOLVED` | Those markets are used, and BIOS reaches a decision |
| Some are European, others are `EMEA` or blank | `PARTIALLY_RESOLVED` | The verified markets are kept. The decision is `NEEDS_CLARIFICATION`, and the rest are suggestions. |
| None are European | `NEEDS_CLARIFICATION` | The decision is `NEEDS_CLARIFICATION`, and related markets are suggestions |

**With the current workbook, a Europe request always returns `NEEDS_CLARIFICATION`.** The workbook never mentions Europe, so it doesn't establish that any market is European. BIOS suggests `DE`, `ES`, `FI`, `FR`, `IT`, `SE` and `UK` only because the catalog records them as `EMEA`, and the general meaning of that code includes Europe. That meaning isn't in the catalog, so these markets stay unverified until the user confirms them. To get results today, name the markets or ask for `EMEA`. If the data later records European regions, the same code resolves them with no change.

### Unresolved geography

Any stated geography that can't be fully resolved returns `NEEDS_CLARIFICATION` with no target asset. This includes `Sales in America` and `Sales in Finland and Europe`. Resolved markets such as `FI` are kept and named in the next steps. A request that names no geography isn't ambiguous, and it continues as normal.

The geography status describes geography only. In `IT budget dashboard`, nothing shows that `IT` means a place, so the status is `NOT_SPECIFIED`. The open question is recorded separately in `intent.ambiguities` with category `term`, and the decision is still `NEEDS_CLARIFICATION` until the user says whether it means the market.

### Requests with no product

A request that names no product is never pointed at one product's asset. BIOS targets an asset only if all of these are true:

- Its scope is portfolio-wide, such as `All Pharma`.
- It's active and owned, and it has a semantic model.
- `asset_kpi_map` confirms a requested KPI, or its title contains the metric as a whole phrase.

Title-only evidence lowers confidence and is disclosed in the rationale. `Sales in Finland` returns `MODIFY AST-0022` on that basis. Otherwise, as with `Sales in US`, the decision is `NEEDS_CLARIFICATION`, and the matching assets are listed as options once a product is named.

### Governance scope

`blockers` and `warnings` are specific to the request. They cover KPIs the user asked for, assets matching the request's products and markets, and any asset BIOS may recommend as a target, which is a direct dependency.

Findings on other candidate assets go to `out_of_scope_finding_ids` and `out_of_scope_warnings`. They stay visible but don't block the request or appear in the LLM narrative's facts. A stated geography limits this scope even when none of it resolved, while a request with no geography keeps its product-wide scope.

## Reading execution traces

Each row in `agent_execution_traces` has an `execution_metadata_json` value, also returned by `GET /api/v1/assistant/requests/{request_id}/trace`.

| Field | Meaning |
|---|---|
| `execution_mode` | `LLM_ASSISTED`: a real call succeeded and passed validation |
| | `DETERMINISTIC`: no call was attempted, by design or by configuration |
| | `DETERMINISTIC_FALLBACK`: a call was wanted, but the provider was unavailable, failed, or its output was rejected |
| `provider`, `model` | What actually served the step |
| `fallback_reason` | Why the model wasn't used |
| `llm_calls[]` | Status, attempts, duration, tokens, model load time and processor for each call |

## GPU or CPU

BIOS reads placement from Ollama's `/api/ps` after each successful call and never assumes a GPU:

| `processor` | Meaning |
|---|---|
| `gpu` | The whole model is in GPU memory (`size_vram` equals `size`) |
| `mixed` | The model is split between GPU and system memory, which is slower |
| `cpu` | Nothing is in GPU memory |
| `unknown` | Ollama didn't report the model |

`/api/ps` doesn't name the device. To see which GPU Ollama chose, search its log for `inference compute`:

```powershell
Select-String -Path "$env:LOCALAPPDATA\Ollama\server*.log" -Pattern 'inference compute' | Select-Object -Last 1
```

Don't rely on a general hardware listing, because a machine can have several GPUs and Ollama may skip some. BIOS never installs GPU drivers or ROCm.

## Choosing a model

Any installed Ollama model that supports JSON-schema output can be tried by setting `OLLAMA_MODEL`. BIOS is tested only with `qwen3.5:4b`, so check any other model with the live test below. A larger model needs more memory, and a larger `OLLAMA_NUM_CTX` raises memory use too.

To enforce one loaded model at a time on the server as well, set `OLLAMA_MAX_LOADED_MODELS=1` in the environment Ollama starts from, then restart Ollama.

## Tests

Ordinary tests mock Ollama and never reach a real model, even when the service is running:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests
```

Run the real inference tests separately:

```powershell
$env:BIOS_RUN_LIVE_OLLAMA = "1"
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ollama_live.py -v -s
Remove-Item Env:BIOS_RUN_LIVE_OLLAMA
```

## Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| `no such column: execution_metadata_json` | The migration hasn't been applied | Run `alembic upgrade head` (Quick start, step 2) |
| Fallback reason says Ollama is not reachable | The service isn't running, or the URL is wrong | Start Ollama, then open `http://localhost:11434/api/version` |
| Fallback reason says the model is not installed | `OLLAMA_MODEL` doesn't match an installed name | Compare it with `ollama list`, or use `ollama pull` |
| `LLMTimeoutError` on the first call | The model is still loading, or inference is on the CPU | Check `processor` on the trace, then raise `OLLAMA_TIMEOUT_SECONDS` |
| `processor` is `cpu` or `mixed` and runs are slow | GPU memory is short, or Ollama didn't detect the GPU | Close other GPU applications, check the Ollama log, or lower `OLLAMA_NUM_CTX` |
| `invalid_output` on the trace | The model's answer failed schema validation after retries | BIOS falls back automatically. If it happens often, try another model. |
| `ollama` not found in Git Bash | The command isn't on that shell's `PATH` | Use PowerShell. The API doesn't depend on the command. |
| Requests take about 6 seconds longer while Ollama is stopped | Each LLM-assisted agent checks availability before falling back | Start Ollama, or set `BIOS_LLM_PROVIDER=deterministic` |

## Known limitations

- **Narrative accuracy:** the narrative check catches contradictions in the echoed fields and unknown IDs. It can't verify every statement in the prose, so treat `llm_narrative` as advisory.
- **KPI review:** on current tests the model mostly answers `uncertain`, which is cautious but adds limited insight.
- **Mode differences:** an accepted KPI, dimension or time period can still change the normalized intent, and so the decision. For example, the model may map `budget` to `Budget Variance`. Products and markets can't change, and every accepted item is recorded in `intent.resolution`.
- **Unknown product names:** a product the catalog doesn't have, such as `Madeupzol`, is reported as missing scope, not as an unknown product, and the request can still match assets on market and metric.
- **Demonyms:** `German` or `Japanese` aren't read as markets, so they're reported as missing geography.
- **Throughput:** inference runs one agent at a time, and API requests wait for it.
