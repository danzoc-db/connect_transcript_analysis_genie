# Architecture Decision Records

Each record states the context, the decision, and the alternatives considered. Facts marked
"verified" were tested against a live Azure Databricks workspace on 9 Oct 2026.

---

## ADR-1: Self-hosted open model behind a Unity AI Gateway model service (not ai_analyze_sentiment, not hosted Claude)

**Context.** The target workspace runs in Azure UK South **without cross-geo processing**.
`ai_analyze_sentiment` is unavailable there. Databricks-hosted Claude is pay-per-token only on
Azure (verified: `optimizable: false` for provisioned throughput) and is served outside the
workspace geography (verified on a Central US workspace: responses report `us.anthropic.*`).
The customer also wants their own endpoint, monitored through the latest Unity AI Gateway.

**Decision.**
- Host `system.ai.gpt-oss-20b` on our own **provisioned-throughput** serving endpoint (switched
  from `gpt-oss-120b` on 9 Oct 2026 for cost: optimization info `dbus: 53` vs `71`). Verified:
  PT-eligible and `is_cross_geo: false`, so inference stays in the workspace geography.
  Auto-wake scale-to-zero is **not** a field on the model-unit PT API. Idle cost is zero only
  when `provisioned_model_units` is set to `0` (requests then 429 until it is set back to 50).
- Put a **Unity AI Gateway model service** (`transcript_sentiment`, a Unity Catalog securable) in
  front of it, with a provisioned-throughput destination, rate limits, an inference table and
  EXECUTE grants. Every sentiment call goes through the model service.
- Return exactly the `ai_analyze_sentiment` contract (`positive` / `negative` / `neutral` /
  `mixed` / NULL), so downstream SQL, metric views and Genie are unchanged if the customer later
  gets `ai_analyze_sentiment` back.

**Consequence.** `ai_query` cannot target a custom model service yet (verified: 404), so
sentiment is scored by a Python job task calling the gateway route
`/ai-gateway/mlflow/v1/chat/completions` rather than inside the SQL pipeline. When `ai_query`
supports model services, the task can become one SQL statement without changing the contract.

The current DAB provider does not use the model-unit PT update API. The endpoint is therefore
bootstrapped and resized through `scripts/manage_pt_endpoint.py`; the rest of the architecture
remains bundle-managed.

**Alternatives considered.**
| Option | Why not |
|---|---|
| `ai_analyze_sentiment` | Blocked without cross-geo processing. |
| `ai_query` on `system.ai` Claude | Pay-per-token only on Azure, served outside the geography. |
| `ai_query` straight to the PT endpoint | Works, but bypasses the Unity AI Gateway model service, so there are no service-level rate limits, fallback or `system.ai_gateway.usage` attribution for pipeline traffic. |
| Classic endpoint `ai_gateway:` block (usage tracking, inference tables) | Previous-generation governance; the model service is the Unity Catalog-native control point. |
| External model (e.g. a cloud provider's hosted LLM) | Out of scope by decision: Databricks-hosted only. |

---

## ADR-2: Sentiment as a separate job task with MERGE (not a streaming table)

**Context.** Scoring costs model-unit time, and transcripts never change after landing.

**Decision.** `score_sentiment` anti-joins silver against the sentiment table, scores only new
contacts, and MERGEs on `contact_id`. Bounded concurrency plus retry/backoff handles 429s.
Idle endpoints are parked at `provisioned_model_units: 0` (429s, no auto-wake); the job scales
to 50 units before scoring.

Each contact is scored on **customer speech only**. Opening is the initial problem statement,
middle contains substantive responses while the resolution develops, and closing is the final
substantive response. Scripted goodbye text is excluded. The full substantive customer text is
also scored. This gives a within-call trajectory for Genie without a turn-level fact table or
one model call per utterance.

**Alternative.** A streaming table with `ai_query` (blocked by ADR-1). A pipeline full refresh
would also re-score everything, which this design avoids.

---

## ADR-3: Unity Catalog metric view as the gold layer (not a BI semantic model)

**Decision.** KPIs (negative share, net sentiment score, transfer rate, hold time and, in the
live demo, sentiment recovery rate) are defined once in a metric view (YAML 1.1) and published
by a SQL task. Genie, dashboards and SQL all read the same definitions. Materialization is used
where the workspace supports it.

**Alternative.** Per-tool measures (DAX, Copilot prompts), which drift and cannot be reviewed in a PR.

---

## ADR-4: Domain via governed tags, managed by a job task

**Context.** Unity Catalog domains (Beta) have a REST API and CLI but no bundle resource.
A domain is backed by a governed tag; assets join it by carrying the tag.

**Decision.** One-off creation of the tag policy and domain (Customer Experience > Contact Centre)
by an admin bootstrap script; an idempotent job task tags the silver tables, the metric view and
the Genie space on every run, so new assets cannot drift out of the domain.

---

## ADR-5: CI identity and job identity

**Decision.** A deploy service principal (CAN_MANAGE, used only by GitHub Actions) and a runtime
service principal (`run_as` for the job, data and model-service privileges only). Humans get
CAN_MANAGE_RUN (engineers) or CAN_VIEW (analysts). Production-mode bundles stop config being
edited in the UI, so every change goes through a PR.

For the demo, CI authenticates with an OAuth M2M secret. The recommended customer setup is
**GitHub OIDC workload identity federation** (no stored secret), documented in GETTING_STARTED.
