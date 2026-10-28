# Agent Rules for Connect Transcript Analysis + Genie

<!--
SYNC NOTE: This file is the cross-tool mirror of `.cursorrules`.
Both files MUST stay in sync. If you change one, change the other in the same PR.
Loaded automatically by:
  - Claude Code        (AGENTS.md)
  - OpenAI Codex CLI   (AGENTS.md)
  - Cursor             (.cursorrules; recent versions also read AGENTS.md)
Content below is identical to `.cursorrules`.
-->

## Mission

This repository is the **Connect Transcript Analysis + Genie** demo: Amazon Connect call
transcripts land in a Unity Catalog volume, are ingested with Auto Loader, quality-checked,
scored for sentiment by a **Databricks-hosted open model (`gpt-oss-20b`) on our own
provisioned-throughput serving endpoint, governed by a Unity AI Gateway model service**,
published as a **Unity Catalog metric view**, and queried in natural language through a
**Genie space**. Everything is deployed with **Databricks Asset Bundles** from **GitHub Actions**.

The repo is **public** and targets **external customer sharing**. All code, docs, and config
must be free of internal or customer-identifying data and deployable to any Databricks workspace.

**All data is synthetic.** The generator invents every transcript for the fictional company
"Northwind Energy". The repo must never wire to a real workspace, customer system or
customer-named asset. Read `docs/architecture-decisions.md` for the design rationale.

## Golden Rules

* Don't put emojis in SQL, Python, or general code files
* **ASCII only** in every file (0x00-0x7F). No em dashes, curly quotes, accented letters, or currency symbols (write the currency as a word).
* **Fictional data only.** Use only the fictional brand "Northwind Energy" and invented names, regions and IDs. Never reference a real company, customer, workspace, profile, warehouse, service principal or repository in code, docs, commit messages or PR text.
* **No live wiring.** Public CI stays offline. Workspace values are supplied at deploy time, never committed. The deploy workflow lives in `templates/github-actions/`.
* **NEVER GIVE UP!** Always investigate thoroughly before concluding something is missing or broken
  * Always search with CLI/API, check multiple sources, verify before concluding
  * If something worked before and "disappeared", it's likely still there - just hidden
* Do not hallucinate - verify against the actual code or a live API call before making claims
* **ALWAYS ask before committing** - never `git commit` or `git push` without explicit user approval
* **ALWAYS try programmatic approaches before suggesting manual/UI steps** - check the SDK, REST API, CLI, and bundle schema (`databricks bundle schema`) BEFORE concluding something needs manual action

## Repo-Specific Rules

* **Workspace portability** - all scripts, notebooks, and SQL take `catalog`, `schema`, and
  model-service names as parameters. No hard-coded workspace IDs, catalog names, or user emails
  outside `databricks.yml` target overrides.
* **Keep databricks.yml variables clean** - workspace-specific values go in target overrides,
  not the root `variables:` block.
* **Sentiment contract is fixed** - the `sentiment` columns must return exactly what
  `ai_analyze_sentiment` returns: STRING, one of `positive`, `negative`, `neutral`, `mixed`, or `NULL`.
  Do NOT call `ai_analyze_sentiment` (blocked without cross-geo processing). Call the Unity AI
  Gateway model service with a strict JSON schema (see `docs/architecture-decisions.md`).
* **Unity AI Gateway, not classic endpoint gateways** - use ONE Databricks-hosted
  provisioned-throughput endpoint serving `system.ai.gpt-oss-20b`. The current DAB provider uses
  the wrong API for model-unit PT, so `scripts/manage_pt_endpoint.py` owns endpoint creation and
  resizing outside bundle state. Idle means `provisioned_model_units: 0` and does not auto-wake.
  Do NOT add an endpoint `ai_gateway:` block. Governance lives in the Unity AI Gateway model
  service (`resources.model_services`) that routes to the endpoint, and all pipeline traffic goes
  through that model service. No external models, no cross-geo models. See ADR-1.
* **Secrets in GitHub Actions secrets / Databricks secret scopes only** - never commit tokens.
* **Lint before opening a PR:** `ruff check . && ruff format --check .` and `databricks bundle validate -t dev`
* **Don't over-document** - keep docs neat and consolidated. Internal dev notes go in `docs/internal/` (gitignored).

## Architecture Notes

* **Data generator:** `scripts/generate_synthetic_data.py` (Amazon Connect Contact Lens JSON layout)
* **Pipeline:** Lakeflow Spark Declarative Pipeline SQL (`pipelines/`)
* **Semantics:** Metric view YAML + SQL (`sql/`)
* **Governance tasks:** domain, governed tags, grants (`notebooks/`)
* **Genie:** `genie/*.geniespace.json` deployed by the `genie_spaces` bundle resource
* **Deployment:** Databricks Asset Bundles (`databricks.yml`, `resources/`), CI in `.github/workflows/`

## Branch, Commit & Secrets Conventions

* Branch from an up-to-date `main`; never commit directly to `main`.
* Branch naming: `feat/<work>` for new work, `fix/<fix>` for fixes. All lowercase.
* Squash-merge only; write a meaningful PR title/description.
* **Never commit secrets** (tokens, API keys, passwords). Use a gitignored `.env.local`.
* If you're "vibe coding", read [`AI_CODING_GOTCHAS.md`](AI_CODING_GOTCHAS.md) first.

## Databricks AI Dev Kit

* For Databricks-specific development patterns and best practices, refer to the
  **Databricks AI Dev Kit**: https://github.com/databricks-solutions/ai-dev-kit
* It provides markdown skills and MCP tools for SDP pipelines, Unity Catalog, Jobs,
  AI/BI Dashboards, Genie Spaces, MLflow, Model Serving, Databricks Apps, and more.
