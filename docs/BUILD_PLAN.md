# Build Plan: Connect Transcript Analysis + Genie

Handoff from the research/planning session (9 Oct 2026) to the build session in Cursor.
Read this end to end before writing code. Section 2 lists facts **verified against the live
workspace**; prefer them over anything you remember from training data.

---

## 0. The story this demo tells

> "Your contact centre already records every call in Amazon Connect. Instead of exporting
> transcripts to a Copilot agent outside your governance boundary, land them in Unity Catalog,
> score sentiment with a model you host yourself, inside your workspace's geography, behind
> Unity AI Gateway, publish the KPIs once as a metric view, and let the business ask Genie.
> Every step is code in GitHub, deployed by CI, and a new KPI is a pull request away."

The risk being countered: the customer's teams use Copilot agents to analyse sentiment ad hoc
(ungoverned, unrepeatable, no lineage, no cost attribution). The demo shows the governed,
repeatable alternative, end to end, in a public repo the customer can fork.

Why not `ai_analyze_sentiment`: the customer's workspace (Azure UK South) does not have
cross-geo processing enabled, so `ai_analyze_sentiment` is unavailable to them. Databricks-hosted
Claude is also pay-per-token only on Azure (not eligible for provisioned throughput) and on our
workspace is served from US infrastructure, so it is not a residency-safe substitute either.
The answer is an open model the customer hosts on their own provisioned-throughput endpoint,
which runs in the workspace's geography (`is_cross_geo: false`).

Live moment in the room: open the workspace **Git folder**, use **Genie Code** to add the
**sentiment recovery rate** measure to the metric view, commit on a branch, open a PR, watch
**GitHub Actions** validate and deploy, then ask Genie the new question. See
`docs/LIVE_DEMO_CHANGE.md`.

---

## 1. Decisions already made (do not re-litigate)

| Topic | Decision |
|---|---|
| Workspace | Azure Databricks CLI profile (name in gitignored `docs/internal/workspace.md`). Metastore `metastore_azure_centralus`. UK South residency is covered in docs/talk track, not shown live. |
| GitHub | Public repo `danzoc-db/connect_transcript_analysis_genie`. Use **HTTPS** remotes (SSH auth fails for this account). |
| Catalog | `contact_centre_analytics` (renamed from the empty catalog that already existed; owned by the user, managed location set). Schema `connect_analytics` (prod) is created by the bundle. |
| Domain | Unity Catalog domain **Customer Experience**, subdomain **Contact Centre**. Domain = governed tag. |
| Model | **Databricks-hosted `system.ai.gpt-oss-20b`** on our own **provisioned-throughput serving endpoint** (switched from 120b on 9 Oct 2026 for cost). Same PT rules as 120b: no auto-wake scale-to-zero; idle by setting `provisioned_model_units: 0`. No Claude, no external models, no cross-geo models. |
| Gateway | **Unity AI Gateway model service** `transcript_sentiment` (destination type `DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL` -> our endpoint) with rate limits and an inference table. ALL sentiment traffic goes through it (ADR-1). |
| Sentiment step | **Python job task** (`score_sentiment`) calling the model service over the gateway REST route, because `ai_query` cannot target a custom model service yet. Swap to `ai_query('<catalog>.<schema>.transcript_sentiment')` in SQL once that is supported. |
| Sentiment output | Identical contract to `ai_analyze_sentiment`: STRING in {`positive`,`negative`,`neutral`,`mixed`} or NULL. `ai_analyze_sentiment` itself is NOT used. |
| Conversation windows | Score **customer speech only** (never agent). Four texts per contact: overall substantive `customer_text`; the opening problem statement; the middle responses while a resolution develops; and the final substantive response. Exclude scripted goodbye text. Mid is NULL when there is no middle section. Do not score every turn: cost scales with turns and the metric view stays one row per contact. |
| CI auth | Dedicated deploy service principal with a **workspace-level OAuth secret** (M2M) stored as GitHub Actions secrets. GitHub **OIDC workload identity federation** is documented in the getting-started guide as the customer's target pattern (needs account admin). |
| Live change | "Sentiment recovery rate" measure. Build and test it first, then remove it from `main` and keep the exact change saved for the live demo. |
| Repo layout | Mirrors `danzoc-db/fe_bar_submission_energy_theft_detection` conventions (AGENTS.md/.cursorrules mirror, AI_CODING_GOTCHAS, numbered notebooks, `pipelines/`, `scripts/`, `docs/` with ADRs). |

---

## 2. Verified facts (live workspace, 9 Oct 2026, Databricks CLI v1.17.0)

### 2.0 The model: gpt-oss-20b on provisioned throughput (the chosen path)
- **Chosen model (user, 9 Oct 2026):** `system.ai.gpt-oss-20b` v1, provisioned throughput, 50 model units while scoring. The current endpoint is `connect-sentiment-gpt-oss-20b`, serving entity `gpt-oss-20b` / `system.ai.gpt-oss-20b` v1, `min_dbus: 53.5713`, `type: PT_FOUNDATION_MODEL`. The model service destination `gpt_oss_20b_pt` points to this endpoint.
- `GET /api/2.0/serving-endpoints/get-model-optimization-info/system.ai.gpt-oss-20b/1` returned:
  `optimizable: true, on_demand_pt_eligible: true, reserved_pt_eligible: false, is_cross_geo: false, model_unit_chunk_size: 50, max_model_units_per_pt_endpoint: 2000, dbus: 53`.
  Same check for `system.ai.gpt-oss-120b` v1 (earlier probe, not the chosen model): eligible, `is_cross_geo: false`, `model_unit_chunk_size: 50`, `dbus: 71`. Llama 3.3 70B (`system.ai.llama_v3_3_70b_instruct` v1): eligible, `is_cross_geo: false`, **throughput bands** (`throughput_chunk_size: 9500`, optimized band `throughput: 2400`, `dbus: 85`), not model units.
- Same check for every Databricks-hosted Claude model (sonnet-4-6, sonnet-4-5, haiku-4-5): **not eligible** (`optimizable: false`). That is why Claude is out.
- Served-entity fields available in the bundle schema: `entity_name`, `entity_version`, `provisioned_model_units`, `scale_to_zero_enabled`, `burst_scaling_enabled`, `min/max_provisioned_throughput`, `workload_type`.
- **Phase 3 step 0 result (9 Oct 2026, ~15:56-15:00 UTC):**
  - First probe used `system.ai.gpt-oss-120b` **v1**; user then switched the same endpoint to `system.ai.gpt-oss-20b` **v1** (only version for both).
  - Create MUST use `POST /api/2.0/serving-endpoints/pt` (`databricks serving-endpoints create-provisioned-throughput-endpoint`). The classic `POST /api/2.0/serving-endpoints` rejects this model with `workloadSizeId is undefined`.
  - `PtServedModel` accepted fields: `entity_name`, `entity_version`, `name`, `provisioned_model_units`, `burst_scaling_enabled`. **`scale_to_zero_enabled` is not a field on this API.** CLI warning: `unknown field: scale_to_zero_enabled` (stripped). Same on `PUT /api/2.0/serving-endpoints/pt/{name}/config`. Classic `update-config` on a PT endpoint: `Provisioned throughput endpoints created using the /serving-endpoints/pt path cannot be updated with this API`.
  - **Post-create `scale_to_zero_enabled` still does not exist.** A raw `PUT /api/2.0/serving-endpoints/pt/{name}/config` with that flag returned HTTP 200 but the field was dropped.
  - **What the Serving UI "scale from 0" actually did (user, 9 Oct 2026):** it set `provisioned_model_units: 0` (`min_dbus: 0.0`, config_version 5+). The API accepts that value: `PUT .../pt/{name}/config` with `provisioned_model_units: 0` round-trips. There is still no min/max pair and no `scale_to_zero_enabled` on GET.
  - **PMU=0 is parked capacity, not wake-on-traffic.** A gateway request while PMU=0 returned **HTTP 429 in 1.16s**: `REQUEST_LIMIT_EXCEEDED: Workload exceeded model unit rate limit for 'connect-sentiment-gpt-oss-120b'`. Endpoint state stayed `READY` / `DEPLOYMENT_READY` / `pmu: 0`. It did not scale up. To serve, PUT `provisioned_model_units` back to 50 (or another positive multiple of 50). Idle cost at PMU=0 is `min_dbus: 0`.
  - Endpoint created: `connect-sentiment-gpt-oss-20b`. The scoring task changes it from 0 to 50, and back to 0 in a `finally` block.
  - Unity AI Gateway model service created: `contact_centre_analytics.connect_analytics_dev.transcript_sentiment`. Destination type `DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL` -> `serving-endpoints/connect-sentiment-gpt-oss-20b`. Inference table `contact_centre_analytics.connect_analytics_dev.transcript_sentiment_payload`. Supported APIs: `mlflow/v1/chat/completions`, `mlflow/v1/responses`.
  - One request: `POST {host}/ai-gateway/mlflow/v1/chat/completions` with `model=contact_centre_analytics.connect_analytics_dev.transcript_sentiment`, strict JSON schema, `temperature: 0`, `max_tokens: 800`. **HTTP 200 in 1.83s** (endpoint already warm). Response `model: system.ai.gpt-oss-120b-1`. Content is a list: a `reasoning` part plus `text` `{"sentiment": "neutral"}` for a flat meter-reading utterance (parse the final JSON text item, not the reasoning). Usage: 240 prompt + 87 completion tokens.
  - **Current idle policy:** PMU=0 when idle (free); PUT 50 before scoring. Auto-wake STZ does not exist.
  - **DAB provider limitation verified 12 Oct 2026:** the current provider sends model-unit changes through the classic serving endpoint API. Removing its binding can also delete the endpoint. Therefore this endpoint is intentionally outside bundle state and is managed by `scripts/manage_pt_endpoint.py` through `POST /api/2.0/serving-endpoints/pt` and `PUT /api/2.0/serving-endpoints/pt/{name}/config`.
- Structured output works on the pay-per-token `databricks-gpt-oss-120b` (tested via `ai_query` with the strict JSON schema below): returns `{"sentiment": "mixed"}` etc. **Prompt tuning needed:** it labelled a flat meter-reading call "positive" instead of "neutral" on that earlier PPT test. The PT gateway probe with an explicit "neutral = factual administrative call" line returned `neutral` for the same kind of utterance. Still give 2-3 few-shot examples and measure agreement against the generator's ground-truth labels (Phase 2).
- gpt-oss is a reasoning model: set `max_tokens` generously enough for reasoning plus the JSON, and parse only the final JSON text item (not the reasoning summary).

### 2.1 Claude via ai_query (researched, NOT used; kept for context)
- **Batch-capable** in `ai_query` (tested OK): `databricks-claude-sonnet-4-6`, `databricks-claude-sonnet-4-5`, `databricks-claude-opus-4-6`, `databricks-claude-haiku-4-5`.
- **NOT batch-capable** (error `Endpoint ... is not supported for batch inference`): `databricks-claude-sonnet-5-5`, `databricks-claude-sonnet-5`, `databricks-claude-haiku-5-5`.
- `ai_query('system.ai.claude-sonnet-4-6', prompt, failOnError => false)` **works** (Unity AI Gateway system model service name).
- Strict structured output works:
  ```sql
  ai_query('system.ai.claude-sonnet-4-6', <prompt>,
    responseFormat => '{"type":"json_schema","json_schema":{"name":"sentiment","schema":{"type":"object","properties":{"sentiment":{"type":"string","enum":["positive","negative","neutral","mixed"]}},"required":["sentiment"]},"strict":true}}',
    failOnError => false)
  -- returns STRUCT<result STRING, errorMessage STRING>; result = '{"sentiment":"mixed"}'
  ```
- The model echoed back as `us.anthropic.claude-sonnet-4-6`: on this (Central US) workspace Claude is served from US infrastructure. Useful honesty point for the residency conversation.

### 2.2 Unity AI Gateway model services (the "latest gateway")
- REST: `/api/2.1/unity-catalog/model-services`. CLI: `databricks ai-gateway create-model-service PARENT MODEL_SERVICE_ID --json @file`. DABs resource: `resources.model_services` (keys: `parent`, `model_service_id`, `comment`, `config`, `grants`, `lifecycle`).
- `parent` format: `schemas/<catalog>.<schema>`. Resource name: `model-services/<catalog>.<schema>.<service>`.
- This config was **created successfully** (then deleted):
  ```json
  {"config":{
    "routing":{
      "destinations":[{"name":"claude_sonnet","destination_type":"DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL","pay_per_token_config":{"model":"models/system.ai.databricks-claude-sonnet-4-6"}}],
      "fallback":{"destinations":[{"name":"claude_haiku","destination_type":"DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL","pay_per_token_config":{"model":"models/system.ai.databricks-claude-haiku-4-5"}}]}},
    "inference_table":{"parent":"schemas/<catalog>.<schema>","table_name_prefix":"transcript_sentiment"},
    "rate_limits":[{"key":"RATE_LIMIT_KEY_SERVICE","renewal_period":"RATE_LIMIT_RENEWAL_PERIOD_MINUTE","requests":600}]}}
  ```
  Inference table is created as `<catalog>.<schema>.<prefix>_payload`.
  (That probe routed to pay-per-token Claude. For this build use the provisioned-throughput destination instead.)
- **Provisioned-throughput destination (what we use):**
  ```yaml
  destinations:
    - name: gpt_oss_20b_pt
      destination_type: DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL
      provisioned_throughput_config:
        model_serving_endpoint: serving-endpoints/<endpoint name>
  ```
  Per the schema: "sizing (provisioned throughput, burst scaling, model version) is owned by the Model Serving endpoint itself"; "the endpoint must exist at create time". The deployment workflow therefore runs `scripts/manage_pt_endpoint.py --units 0` before bundle deployment. Creating a PT destination requires CAN_MANAGE on the endpoint.
  No fallback for now (20b is the only destination). Only in-geo models may be fallbacks if we add one later.
- Rate-limit enums: keys `RATE_LIMIT_KEY_SERVICE | _USER | _USER_DEFAULT | _USER_GROUP | _SERVICE_PRINCIPAL`; periods `RATE_LIMIT_RENEWAL_PERIOD_MINUTE | _HOUR`; limit by `requests` and/or `tokens`.
- **`ai_query` cannot target a custom model service yet.** Both `ai_query('cat.sch.svc', ...)` and `ai_query('model-services/cat.sch.svc', ...)` return 404 (resolved as a serving endpoint). This is why the sentiment step is a Python task calling the gateway REST route (ADR-1).
- A custom model service **is** callable over REST: `POST /ai-gateway/mlflow/v1/chat/completions` with body `{"model":"<catalog>.<schema>.<service>","messages":[...]}` (OpenAI-compatible). This is the route the `score_sentiment` task uses (verified with a pay-per-token destination; re-verify with the PT destination).
- Observability: `system.ai_gateway.usage` (also `system.ai_gateway.external_model_spend`). Columns include `event_time, service_type, service_name, destination_name, destination_model, requester, requester_type, api_type, input_tokens, output_tokens, total_tokens, latency_ms, status_code, invocation_metadata (STRUCT: source), request_tags, routing_information`. `invocation_metadata.source` values seen: `AI_QUERY`, `EXTERNAL_CLIENT`, `DATABRICKS_APPS`, `AI_PLAYGROUND`, `GUARDRAIL`, `ROUTER`. Rows land with a lag (not visible within ~10 min of the call).
- Request tags must be JSON in the `Databricks-Ai-Gateway-Request-Tags` HTTP header. A `request_tags` body field is rejected.
- Permissions (from docs, **verify the GRANT syntax live**): `EXECUTE` on the model service plus `USE CATALOG` / `USE SCHEMA`. Creating needs `CREATE_SERVICE` on the schema; an inference table needs `CREATE_TABLE`.
- Do NOT use the classic pattern (`model_serving_endpoints` + `ai_gateway: {usage_tracking_config, inference_table_config}`) that the energy-theft repo uses.

### 2.3 Domains (Beta)
- CLI: `databricks domains create-domain TAG_KEY --domain-id <id> --subtitle ... --description ... [--parent-domain-id <id>]`, plus `list-domains / get-domain / update-domain / delete-domain`. REST: `/api/2.0/domains`.
- A domain **is backed by a governed tag** (tag policy, `databricks tag-policies ...`). Existing example: domain `eved` has `tag_key: "eved"`; its subdomain `eved-real-driving` has `parent_domain_id: "eved"` and `tag_key: "eved/Real Driving"`.
- Assets join a domain by carrying the governed tag:
  - UC tables / views / metric views: `ALTER TABLE ... SET TAGS ('<key>' = '<value>')` or `databricks entity-tag-assignments create ENTITY_NAME TAG_KEY ENTITY_TYPE --tag-value ...`
  - Genie spaces: `databricks workspace-entity-tag-assignments create-tag-assignment geniespaces <space_id> <tag_key> --tag-value ...` (entity types allowed: apps, dashboards, geniespaces, notebooks)
- **To verify in the build**: whether a subdomain's `"parent/Child"` tag_key is applied as key=`parent`, value=`Child`. Create the domain, tag one table, and confirm it appears under the subdomain in Discover before wiring the rest.
- Not a DABs resource. Create/update it idempotently from a governance task (Phase 5).

### 2.4 Bundles
- `databricks bundle schema` in CLI v1.17.0 includes: `genie_spaces`, `model_services`, `model_provider_services`, `pipelines`, `jobs`, `schemas`, `volumes`, `sql_warehouses`, `secret_scopes`, and more. No `domains`.
- `genie_spaces` keys: `title, description, warehouse_id, parent_path, file_path (.geniespace.json), serialized_space, permissions, lifecycle`.
- Export an existing space to bootstrap the JSON: `databricks bundle generate genie-space --existing-id <space_id>`. Recommended: build the space once in the UI, export it, commit the JSON, then manage it as code.
- Metric-view YAML 1.1 materialization was verified on 12 Oct 2026. The `daily_queue_metrics` aggregated materialization refreshed successfully in relaxed mode.

### 2.5 Workspace inventory
- Warehouses: `Serverless Starter Warehouse` (`4c992f1d4de33244`), `Energy Theft Demo Warehouse` (`16de76f2a615a8aa`). Both serverless. Prefer creating a dedicated `sql_warehouses` resource in the bundle (small, auto-stop 10 min) so Genie usage is attributable.
- Workspace GitHub credential exists for the user (`git-credentials list`: provider gitHub, default). A Git folder can be created with `databricks repos create <https url> gitHub --path /Workspace/Users/<user>/connect_transcript_analysis_genie`.
- The user is a workspace admin. Service principals can be created in the workspace, and `databricks service-principal-secrets-proxy` creates OAuth secrets at workspace level.
- Local `gh` auth for `danzoc-db` has scopes `gist, read:org, repo` and **lacks `workflow`**. Pushing `.github/workflows/*` will be rejected until the user runs `gh auth refresh -h github.com -s workflow` (with `danzoc-db` active).

### 2.6 Contract for `ai_analyze_sentiment` (the thing being replicated)
- Official SQL function (`docs.databricks.com` language-manual, retrieved 9 Oct 2026): `ai_analyze_sentiment(content STRING) -> STRING`. Value is `'positive'`, `'negative'`, `'neutral'`, or `'mixed'`. Returns `null` if sentiment cannot be detected. Preview; English-tuned; region-limited (batch AI Functions). Databricks may change the underlying model; licenses mentioned are Apache 2.0.
- **Replicate that return contract only.** Do not replicate rumoured internals (Hugging Face tokenizer + BERT/RoBERTa classifier, a `STRUCT<sentiment, confidence>` / probability, or a Pandas UDF wrapping a local classifier). Those do not match the SQL function: no `confidence` column, spelling is `analyze` not `analyse`, and `mixed` is a first-class label a typical 3-class classifier does not have. Our gpt-oss JSON schema stays `{ "sentiment": <enum> }`; errors and unparseable output become NULL. On this workspace the built-in is never called.

### 2.7 End-to-end acceptance evidence (12 Oct 2026)
- Initial load: 60 bronze rows, 57 silver rows and 57 scored rows. Each planted drop expectation failed exactly one input row. All sentiment columns stayed inside the four-label contract and closing-label agreement was 100 percent.
- Idempotent rerun: the scoring task reported `No new contacts; endpoint parked at 0 PMU.`
- Incremental load: `second-drop` added 20 bronze rows, 17 valid silver rows and exactly 17 scored rows. The inference table recorded 68 calls, all tagged with the job ID, run ID, project and task.
- Production validation: all five orchestrated tasks succeeded for a 20-contact batch, the three planted bad records were dropped, all 17 valid contacts were scored, and 68 of 68 tagged model-service calls succeeded. See [`docs/evidence/production-validation.md`](evidence/production-validation.md).
- Metric view: measure queries succeeded, and the `daily_queue_metrics` relaxed materialization refreshed successfully.
- Genie: the deployed space uses the metric view plus the sentiment drill table. API questions for highest negative share and opening-versus-closing sentiment completed successfully with valid `MEASURE()` SQL.
- Governance: the four Unity Catalog data assets and the Genie space carry the exact `customer_experience/Contact Centre` tag.
- Endpoint after both scoring runs: `provisioned_model_units: 0`, `min_dbus: 0`, state `READY`.

---

## 3. Target repo layout

```
connect_transcript_analysis_genie/
  AGENTS.md / .cursorrules           (mirror, done)
  AI_CODING_GOTCHAS.md               (done)
  README.md                          demo overview, architecture diagram, quickstart, demo flow
  LICENSE                            Apache-2.0 (or match the energy-theft repo)
  SECURITY.md                        port from energy-theft repo
  CHANGELOG.md
  databricks.yml                     bundle, variables, targets dev/prod
  resources/
    schema.yml                       schema + volume `raw_transcripts` + grants
    model_serving.yml                PT endpoint (gpt-oss-20b) + Unity AI Gateway model service + grants
    pipeline.yml                     SDP pipeline (serverless)
    job.yml                          4-task job + permissions + run_as
    genie.yml                        genie_spaces resource
    warehouse.yml                    dedicated serverless SQL warehouse
  scripts/
    generate_synthetic_data.py       (drafted, see 4.1 fixes)
    bootstrap_identities.sh          one-off: SPs, groups, OAuth secret, gh secrets
  pipelines/
    01_bronze_transcripts.sql
    02_silver_transcripts.sql
  sql/
    contact_sentiment_metrics.sql    metric view DDL (YAML 1.1), includes commented live-demo measure
  notebooks/
    00_demo_guide.py                 helper notebook: what the demo does, run order, queries to show
    01_land_transcripts.py           thin wrapper calling the generator
    02_score_sentiment.py            calls the model service, MERGEs into silver_transcript_sentiment
    03_register_domain_assets.py     domain + governed tags + Genie tag (idempotent)
    04_gateway_observability.py      system.ai_gateway.usage + inference table queries
  src/connect_sentiment/
    scoring.py                       prompt, JSON schema, contract normaliser, gateway client (unit-testable)
  genie/
    contact_sentiment.geniespace.json
  tests/
    test_generator.py                schema/ASCII/coherence tests, offline
  .github/
    CODEOWNERS                       @danzoc-db
    workflows/ci.yml                 PR: lint + test + bundle validate
    workflows/deploy.yml             main: bundle deploy -t prod + run job
  docs/
    BUILD_PLAN.md                    (this file)
    GETTING_STARTED.md               customer-facing: do this on your own workspace
    architecture-decisions.md        ADRs (drafted)
    LIVE_DEMO_CHANGE.md              the Genie Code live change, prompt + expected diff (drafted)
    demo_architecture.md             diagram + data flow
```

---

## 4. Phased build with acceptance criteria

Work phase by phase. At the end of each phase, run the acceptance check and **stop to show the
user** before moving on. Ask before every commit/push.

### Phase 1: Repo + identities + GitHub
1. Create the public repo: `gh repo create danzoc-db/connect_transcript_analysis_genie --public --description "..."` (ask first). Set the remote to HTTPS.
2. `scripts/bootstrap_identities.sh` (idempotent, `--profile` arg), run once by the user:
   - Groups: `contact_centre_engineers` (CAN_MANAGE_RUN on job, edit pipeline), `contact_centre_analysts` (CAN_VIEW job, SELECT on gold, CAN_RUN Genie).
   - Service principals: `sp-connect-transcript-deploy` (CI identity), `sp-connect-transcript-runtime` (job `run_as`). Grant the deploy SP the **Service Principal User** role on the runtime SP.
   - OAuth secret for the deploy SP via `databricks service-principal-secrets-proxy create <sp_id>`; push to GitHub with `gh secret set DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`, and `gh variable set DATABRICKS_HOST`.
   - UC grants on `contact_centre` to both SPs (USE CATALOG, CREATE SCHEMA for deploy; runtime gets data privileges via the bundle `grants`).
   - Fallback if two SPs are too heavy for the timeline: one SP for deploy + run, clearly flagged in ADR-5.
3. Branch protection on `main` (PR required, CI must pass, CODEOWNERS). Ask before applying.
- **Accept:** `gh repo view` shows public; `databricks service-principals list` shows both SPs; GitHub secrets exist (names only).

### Phase 2: Synthetic Amazon Connect data
1. Fix the drafted generator (`scripts/generate_synthetic_data.py`):
   - **Coherence bug:** opening, agent and reaction lines are drawn independently within a queue, so "book the install" can be followed by "second missed appointment". Restructure each scenario into **sub-intents**, each with its own coherent opening/agent/reaction set.
   - Keep the Contact Lens post-call JSON layout and path `connect/Analysis/Voice/YYYY/MM/DD/<contactId>_analysis_<ts>.json`. No sentiment fields in the source.
   - Add a `--batch_label` / `--contacts` incremental mode so a second, smaller drop can be landed live to show Auto Loader picking up only new files.
   - Ground truth: write the intended arc into a hidden field (e.g. `ContactAttributes.QaArcLabel`), excluded from silver. Use it to measure the model's agreement rate (Phase 4 acceptance) and show it in the demo guide.
   - Default 400 contacts over 60 days. Each contact makes 3 model calls (overall + opening + closing), plus a 4th when there is a middle section (~1,200 to ~1,600 calls per full load). Size the model-service rate limit and thread pool accordingly.
2. `tests/test_generator.py`: valid JSON, ASCII only, no customer name except "BGE", turn ordering, coherence per sub-intent.
- **Accept:** `uv run pytest` green; a sample file reads naturally end to end (show the user 2 samples).

### Phase 3: Bundle skeleton + pipeline (bronze, silver, sentiment)
1. `databricks.yml`: bundle `connect_transcript_analysis_genie`; variables `catalog` (`contact_centre_analytics`), `schema`, `sentiment_base_model` (default `system.ai.gpt-oss-20b`), `sentiment_model_version` (`1`), `sentiment_model_units` (50), `scoring_max_workers` (8), `warehouse_id`, `domain_tag_key`, `domain_tag_value`, `runtime_sp_app_id`. Targets:
   - `dev`: `mode: development`, default, schema `connect_analytics_dev`, user identity.
   - `prod`: `mode: production`, schema `connect_analytics`, `run_as` runtime SP, root path `/Workspace/Shared/.bundle/${bundle.name}/prod`, top-level `permissions` (engineers CAN_MANAGE_RUN... see Phase 4).
2. `resources/schema.yml`: schema + managed volume `raw_transcripts`, with grants (runtime SP READ/WRITE VOLUME, analysts none on bronze).
3. Pipeline (serverless, `catalog`/`schema` set, `configuration` passes `volume_path`):
   - `01_bronze_transcripts.sql`: `CREATE OR REFRESH STREAMING TABLE bronze_connect_transcripts AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at FROM STREAM read_files('${volume_path}/connect/Analysis/Voice', format => 'json', multiLine => true, schemaHints => ...)`. That is Auto Loader under the hood; say so in comments and docs.
   - `02_silver_transcripts.sql`: streaming table with **expectations**, for example:
     - `CONSTRAINT valid_contact_id EXPECT (contact_id IS NOT NULL) ON VIOLATION DROP ROW`
     - `CONSTRAINT has_customer_turns EXPECT (customer_turn_count > 0) ON VIOLATION DROP ROW`
     - `CONSTRAINT completed_job EXPECT (job_status = 'COMPLETED') ON VIOLATION DROP ROW`
     - `CONSTRAINT known_queue EXPECT (queue IN (...)) ` (warn only)
     - `CONSTRAINT plausible_duration EXPECT (duration_seconds BETWEEN 10 AND 7200)` (warn only)
     Flatten to one row per contact: `contact_id, contact_ts, contact_date, queue, contact_reason, agent_id, agent_name, county, segment, hold_seconds, transferred, duration_seconds, turn_count, customer_turn_count, full_transcript, customer_text, customer_opening_text, customer_mid_text, customer_closing_text`. Opening is the first substantive customer turn, closing is the final substantive response, and middle contains the turns between them. Add table and column comments (Genie reads them).
     Plant a few bad records in the generator (null contact id, FAILED job status) so the expectations visibly drop rows in the pipeline UI.
   - Sentiment is NOT in the pipeline (see Phase 4 `score_sentiment`), because the pipeline would need `ai_query`, and `ai_query` cannot target a Unity AI Gateway model service yet.
4. **Step 0 of this phase:** done. Result in section 2.0. Chosen model is now gpt-oss-20b PT. Auto-wake STZ does not exist; idle = `provisioned_model_units: 0`.
- **Accept:** `databricks bundle deploy -t dev` + pipeline run succeed; silver shows dropped-row counts from the planted bad records; PT idle policy (PMU 0 vs 50) is recorded in 2.0.

### Phase 4: Job, permissions, metric view
1. `resources/job.yml`, job `connect-transcript-sentiment`, 5 tasks:
   1. `land_transcripts`: python/notebook task running the generator (`skip_if_exists` true).
   2. `refresh_pipeline`: `pipeline_task` for bronze + silver (never `full_refresh: true`).
   3. `score_sentiment`: notebook `02_score_sentiment.py` (serverless). Logic lives in `src/connect_sentiment/scoring.py`:
      - Select silver rows whose `contact_id` is not yet in `silver_transcript_sentiment` (anti-join), so only new contacts are scored and token spend stays bounded.
      - For each contact, score overall `customer_text`, `customer_opening_text`, and `customer_closing_text`. Also score `customer_mid_text` when it is not NULL. POST `{host}/ai-gateway/mlflow/v1/chat/completions` with `model = <catalog>.<schema>.transcript_sentiment`, `response_format` = the strict JSON schema, `temperature: 0`. Auth with the job identity's token from `WorkspaceClient().config.authenticate()`.
      - Bounded concurrency (thread pool, `max_workers` as a job parameter, default 8), retries with exponential backoff on 429/503. 429 with PMU=0 means the endpoint is parked, not waking: the job (or a prior task) must PUT `provisioned_model_units: 50` before scoring and PUT 0 after.
      - Normalise to the contract: lowercase; anything outside {positive, negative, neutral, mixed} or any error -> NULL, with `sentiment_error` holding the reason.
      - Derived `sentiment_shift`: 'recovered' (opening negative/mixed AND closing positive), 'deteriorated' (opening positive/neutral AND closing negative), else 'stable'.
      - Write with Delta `MERGE` on `contact_id` into `silver_transcript_sentiment` (columns: all silver columns needed by the metric view + `sentiment`, `sentiment_opening`, `sentiment_mid`, `sentiment_closing`, `sentiment_shift`, `sentiment_path` (e.g. `negative>mixed>positive`), `sentiment_model`, `sentiment_service`, `scored_at`, `sentiment_error`). Create the table with comments on first run.
      - Pass `request_tags`/headers if the gateway supports them (e.g. `job_run_id`) so usage rows can be tied to job runs. Verify.
   4. `publish_metric_view`: SQL file task (`sql_task.file`) on the warehouse running `sql/contact_sentiment_metrics.sql`. Parameterise catalog/schema.
   5. `register_domain_assets`: notebook `03_register_domain_assets.py` (Phase 6).
   - Job parameters: `catalog`, `schema`, `contacts`. Serverless environment `client: "2"` or newer. `max_concurrent_runs: 1`, `timeout_seconds`, failure notifications to a parameterised email, tags (`project`, `domain`, `cost_centre`). Daily schedule, PAUSED in dev (development mode does this).
   - Permissions (job-level `permissions`): deploy SP CAN_MANAGE (implicit owner); `contact_centre_engineers` CAN_MANAGE_RUN; `contact_centre_analysts` CAN_VIEW. Pipeline: engineers CAN_RUN, analysts CAN_VIEW. Document in GETTING_STARTED why config changes go through Git + CI rather than UI edits (production mode bundles lock UI editing).
2. `sql/contact_sentiment_metrics.sql`: `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ version: 1.1 ... $$`. Source `silver_transcript_sentiment`. Suggested content:
   - Dimensions: contact_date, contact_week, contact_month, queue, contact_reason, agent_name, county, segment, sentiment, transferred.
   - Measures: `total_contacts`, `negative_contacts`, `negative_share`, `positive_share`, `mixed_share`, `net_sentiment_score` ((positive - negative) / total), `avg_hold_minutes`, `transfer_rate`, `avg_handle_minutes`.
   - `materialization:` block (mode relaxed, aggregated MV on day x queue), per "metric view as a materialized view". Confirm materialization is supported on this workspace; if not, record it and fall back to an explicit `gold_contact_sentiment_daily` materialized view in the pipeline plus the metric view.
   - Include the **live demo measure, commented out** (see `docs/LIVE_DEMO_CHANGE.md`).
   - Check during build whether metric views can be declared inside the SDP pipeline on this workspace. If yes, consider moving the metric view there; otherwise keep the SQL task (current plan).
- **Accept:** job runs green end to end in dev (including a scale-up from PMU=0 to 50 at start and scale-down to 0 at end); every `sentiment*` value is in the contract set with zero rows outside it; a rerun scores 0 new contacts; closing-sentiment agreement with the generator's hidden outcome arc is reported (target: 85%+; tune the prompt or coherent response lines if lower); `SELECT queue, MEASURE(negative_share) FROM ... GROUP BY ALL` returns sensible numbers.

### Phase 5: Model serving endpoint + Unity AI Gateway model service + observability
1. `scripts/manage_pt_endpoint.py`. The model-unit PT endpoint is intentionally managed outside DAB until the provider uses the PT API. Served entity:
   ```yaml
  {
    "name": "connect-sentiment-gpt-oss-20b",
    "config": {
      "served_entities": [{
        "name": "gpt-oss-20b",
        "entity_name": "system.ai.gpt-oss-20b",
        "entity_version": "1",
        "provisioned_model_units": 0
      }]
    }
  }
   ```
   No `ai_gateway:` block and no `scale_to_zero_enabled` (unknown on the PT API). Create/update via `/api/2.0/serving-endpoints/pt`.
2. `model_services.transcript_sentiment`: `parent: schemas/${var.catalog}.<schema>`, routing destination per section 2.2 (PT destination `gpt_oss_20b_pt` -> `serving-endpoints/${var.sentiment_endpoint_name}`), no fallback, rate limit 600 requests per minute, `inference_table` (`parent: schemas/<catalog>.<schema>`, prefix `transcript_sentiment`), and EXECUTE grants to the runtime SP and engineers.
3. Lock down the endpoint so the model service is the only way in: only the runtime SP and engineers hold CAN_QUERY on the endpoint. Check whether the model service needs its own access to the endpoint (it is "delegated to the service owner") and document the result.
4. `notebooks/04_gateway_observability.py` (also linked from the demo guide):
   - `system.ai_gateway.usage` filtered to `service_name = '<catalog>.<schema>.transcript_sentiment'` (confirm the exact value): calls and tokens per day, by `requester` (runtime SP vs humans), by `invocation_metadata.source`, p50/p95 `latency_ms`, error rate by `status_code` (show the 503s during a cold start if they are logged), and `destination_name` (primary vs fallback).
   - The inference table `transcript_sentiment_payload`: sample request/response pairs for 3 contacts.
   - `system.serving.endpoint_usage` / `system.serving.served_entities` for the endpoint itself (cost: model-unit hours, idle time at PMU=0).
   - Optional: an AI/BI dashboard on these queries as a `dashboards` bundle resource.
- **Accept:** usage rows visible for the job's calls through the model service; payloads in the inference table; after the run `provisioned_model_units` is 0 (check GET). Note the usage-table ingestion lag in the demo script.

### Phase 6: Domain + Genie
1. `notebooks/03_register_domain_assets.py` (idempotent, SDK `WorkspaceClient().api_client.do(...)` for Beta endpoints):
   - Ensure tag policy `customer_experience` exists (`tag-policies`), with allowed value `Contact Centre`.
   - Ensure domain `customer-experience` (tag_key `customer_experience`) and subdomain `contact-centre` (parent `customer-experience`, tag_key per 2.3 finding).
   - Tag `silver_connect_transcripts`, `silver_transcript_sentiment`, the metric view, and the Genie space.
   - Requires ASSIGN on the tag policy for the runtime SP. If creating tag policies / domains needs admin rights the SP lacks, split it: one-off creation in `bootstrap_identities.sh` (run by the admin user), and tag assignment only in the job.
2. `resources/genie.yml` + `genie/contact_sentiment.geniespace.json`:
   - Data sources: the metric view (primary), `silver_transcript_sentiment` (for drill-to-transcript questions). Verify Genie accepts a metric view as a data source on this workspace (expected yes; the energy-theft repo's `01d_metric_views.py` + `06_configure_genie.py` are prior art).
   - Text instructions: sentiment definitions = ai_analyze_sentiment contract; "negative share" definition; Irish counties; week starts Monday; never expose full transcripts unless asked.
   - Sample questions: "Which queue had the highest negative share last week?", "Show net sentiment score by week for Billing", "Which agents handle the most negative calls but transfer the fewest?", "Show three example transcripts from negative Boiler Care calls".
   - 3-5 example SQL pairs using `MEASURE()`.
   - Permissions: analysts CAN_RUN, engineers CAN_EDIT, warehouse CAN_USE for analysts.
   - Bootstrap tip: build the space once in the UI, then `databricks bundle generate genie-space --existing-id <id>` and commit.
- **Accept:** the domain shows all 4 assets in Discover; Genie answers all sample questions correctly (run them through the Genie API and save outputs to `docs/evidence/`).

### Phase 7: CI/CD + Git folder
1. `.github/workflows/ci.yml` (on `pull_request`): checkout, `databricks/setup-cli@main`, `uv`/`pip` install ruff + pytest, `ruff check`, `pytest`, `databricks bundle validate -t prod`. Auth env: `DATABRICKS_HOST` (var), `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` (secrets).
2. `.github/workflows/deploy.yml` (on push to `main` + `workflow_dispatch`): `databricks bundle deploy -t prod`, then `databricks bundle run -t prod connect_transcript_sentiment_job --no-wait` (or wait only for the `publish_metric_view` task, so the live demo turnaround is short. Consider a separate lightweight `publish_semantics` job used by CI for metric-view-only changes, triggered by a `paths:` filter on `sql/**`).
3. Include the OIDC variant **commented** in the workflow (`DATABRICKS_AUTH_TYPE: github-oidc`, `permissions: id-token: write`) and document it in GETTING_STARTED as the recommended customer setup.
4. Create the workspace **Git folder** pointing at the public repo (`databricks repos create ... --path /Workspace/Users/<user>/connect_transcript_analysis_genie`). Confirm Genie Code can edit `sql/contact_sentiment_metrics.sql` there and commit to a branch from the Git folder UI.
- **Accept:** a dummy PR runs CI green; merging deploys prod and the job runs as the runtime SP.

### Phase 8: Docs + rehearsal
1. `docs/GETTING_STARTED.md` (customer-facing, generic, no customer name). Sections:
   1. What you get (architecture diagram).
   2. Prerequisites: UC-enabled workspace, serverless, a catalog, permission to create service principals, a GitHub org.
   3. **Data residency on Azure UK South (no cross-geo processing)**: why `ai_analyze_sentiment` and pay-per-token hosted models are unavailable without cross-geo; how to check any model with the `get-model-optimization-info` API (`is_cross_geo`, PT eligibility); why a provisioned-throughput endpoint on an open model runs in-geo; scale-to-zero cost trade-off (cold start vs idle cost); recommend written confirmation from the account team for the exact model, mode and retention. Link `learn.microsoft.com/azure/databricks/resources/designated-services` and the foundation-model compliance page.
   4. Point the volume at real Amazon Connect output: Contact Lens exports to S3, then either a UC external location on S3 (cross-cloud) or a scheduled copy into ADLS; the Auto Loader path is unchanged.
   5. Fork, configure `databricks.yml` targets, create identities (OIDC federation steps), deploy.
   6. Govern the model: Unity AI Gateway model service, grants, rate limits, usage table queries.
   7. Domains + Genie.
   8. Making a change safely (Git folder, Genie Code, PR, CI).
   9. Cost notes: tokens per transcript, streaming-only-new-rows, full refresh warning.
   All links are descriptive hyperlinks to docs.databricks.com / learn.microsoft.com, with no bare URLs and no internal go/ links.
2. `README.md`: hero paragraph, architecture diagram (Mermaid), quickstart (5 commands), demo flow, repo map. Mirror the energy-theft README section order where it applies.
3. `notebooks/00_demo_guide.py`: the presenter's helper notebook (run order, what to click, the queries to show, links to pipeline/job/Genie/domain via `spark.conf` / workspace URL helpers).
4. `docs/demo_architecture.md` + ADRs finalised.
5. Rehearse the live change (`docs/LIVE_DEMO_CHANGE.md`) end to end, timing each step, and record the timings in that doc.
- **Accept:** a fresh reader can follow GETTING_STARTED on a clean workspace (dry-run with `-t dev`); customer-name and non-ASCII greps come back empty; the live change rehearsed in under 10 minutes merge-to-answer.

---

## 5. Open questions to resolve during the build (ask the user if blocked)

0. PT idle for gpt-oss-20b: **no auto-wake STZ** (same as 120b). Idle = `provisioned_model_units: 0`. Serving = PUT 50. Job should scale up / scale down. Chosen model is 20b; do not add a 120b fallback unless asked.
1. Subdomain tag key semantics (`parent/Child` = key/value?), see 2.3.
2. EXECUTE grant syntax on the model service (bundle `grants` vs SQL `GRANT`), and whether the model service needs access to the endpoint itself.
3. Metric view `materialization` availability on this workspace.
4. Whether Genie Code can commit and push from the Git folder directly, or the user commits via the Git folder dialog.
5. The exact `service_name` / `destination_name` values the model service writes to `system.ai_gateway.usage`, and whether request tags (job run id) are supported.
6. Can tag policies and domains be created by an SP, or only by an admin user?

## 6. Things NOT to do
- Do not use `ai_analyze_sentiment` or any `ai_*` task function for sentiment.
- Do not use Claude, external models, or any model that needs cross-geo processing.
- Do not put an `ai_gateway:` block on the serving endpoint; governance is the model service.
- Do not call the serving endpoint directly from the job; always go through the model service.
- Do not leave the PT endpoint at 50 PMU when idle (PUT `provisioned_model_units: 0`). Do not assume auto-wake from 0.
- Do not name the customer anywhere; do not use non-ASCII characters.
- Do not commit or push without asking; do not change branch protection without asking.
- Do not set `full_refresh: true` anywhere.
