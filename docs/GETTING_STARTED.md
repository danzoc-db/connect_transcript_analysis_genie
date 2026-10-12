# Getting Started

## Prerequisites

- A Unity Catalog-enabled Databricks workspace with serverless jobs and pipelines.
- Permission to create schemas, volumes, pipelines, jobs, Genie spaces, model services and a
  provisioned-throughput endpoint.
- A SQL warehouse.
- Databricks CLI 0.281 or later and Python 3.11 or later.
- A GitHub organization or account for CI/CD.

The target model must be available in the workspace region as
`system.ai.gpt-oss-20b` version `1`.

## Data residency and model choice

In an Azure region where cross-geography processing is disabled,
`ai_analyze_sentiment` and some pay-per-token hosted models may be unavailable. This demo uses
an open model on a provisioned-throughput endpoint in the workspace geography, then exposes it
through a Unity AI Gateway model service.

Before deploying, call
`GET /api/2.0/serving-endpoints/get-model-optimization-info/<model>/<version>` and confirm
`is_cross_geo: false` and provisioned-throughput eligibility. Obtain written confirmation for
the exact region, model, serving mode and retention requirements. See
[Azure Databricks designated services](https://learn.microsoft.com/azure/databricks/resources/designated-services)
and [Foundation Model APIs compliance](https://docs.databricks.com/en/machine-learning/foundation-model-apis/compliance.html).

## 1. Configure the targets

Edit only the `dev` and `prod` overrides in `databricks.yml`:

- `workspace.profile`
- `catalog`
- `schema`
- `warehouse_id`
- `runtime_service_principal_name`

The root `variables` block intentionally contains no workspace-specific defaults.

Authenticate and verify the target:

```bash
databricks auth login --host https://your-workspace-host --profile your-profile
databricks current-user me --profile your-profile
databricks bundle validate -t dev
```

## 2. Bootstrap access

Create these workspace-local identities:

- `sp-connect-transcript-deploy`
- `sp-connect-transcript-runtime`
- `contact_centre_engineers`
- `contact_centre_analysts`

The deploy service principal needs the Service Principal User role on the runtime principal.
It also needs USE CATALOG and CREATE SCHEMA on the target catalog.
The runtime principal needs USE CATALOG on the chosen catalog and USE SCHEMA, CREATE TABLE,
MODIFY and SELECT on the deployed schema. It also needs READ VOLUME and WRITE VOLUME on the
landing volume, plus EXECUTE on the model service.

The helper creates workspace-local engineer and analyst groups for resource permissions. For a
production rollout, use account-level groups assigned to the workspace so the same groups can
also receive Unity Catalog privileges.

Run the bootstrap as a workspace admin:

```bash
databricks auth login \
  --host https://accounts.azuredatabricks.net \
  --account-id your-account-id \
  --profile your-account-profile

bash scripts/bootstrap_identities.sh \
  --profile your-profile \
  --account-profile your-account-profile \
  --catalog your-catalog \
  --warehouse-id your-warehouse-id
```

The account profile is required to grant Service Principal User to the deploy identity. If it is
omitted, the script prints the remaining account-admin role assignment.

For this demo, create a workspace OAuth secret for the deploy principal and store these GitHub
settings:

```text
Variable: DATABRICKS_HOST
Variable: DATABRICKS_RUNTIME_CLIENT_ID
Secret:   DATABRICKS_CLIENT_ID
Secret:   DATABRICKS_CLIENT_SECRET
```

For customer deployments, prefer GitHub OIDC workload identity federation. Configure a
Databricks federation policy for the repository, grant `id-token: write` in the workflows, set
`DATABRICKS_AUTH_TYPE: github-oidc`, and remove the stored client secret.

If the workspace enforces an IP access list, GitHub-hosted runner addresses may be blocked.
Register a self-hosted runner on an allowed network, set the repository variable
`DATABRICKS_RUNNER` to its runner label, and set `DATABRICKS_WORKSPACE_CI_ENABLED=true`.
Offline pull-request lint and tests remain on GitHub-hosted runners; workspace bundle validation
and deployment use the network-approved runner.

## 3. Create the parked PT endpoint

The current bundle provider uses the classic serving-endpoint API, which is not valid for this
model-unit endpoint. Create and resize it through the PT API adapter:

```bash
uv run python scripts/manage_pt_endpoint.py \
  --profile your-profile \
  --units 0 \
  --runtime-principal your-runtime-application-id
```

Zero provisioned model units is the verified idle state. It has no auto-wake behavior. The
scoring task explicitly raises capacity to 50, waits until ready, and returns it to zero in a
`finally` block. The runtime principal needs endpoint `CAN_MANAGE` solely for these lifecycle
updates; inference requests still use the governed model-service URL.

Creating or raising the endpoint creates billable capacity. Confirm the action with the
workspace owner first.

## 4. Deploy and run

```bash
databricks bundle deploy -t dev
databricks bundle run -t dev connect_transcript_sentiment_job \
  --params contacts=60,batch_label=initial
```

The workflow:

1. Generates coherent Contact Lens JSON and writes it to the Unity Catalog volume.
2. Refreshes bronze and silver streaming tables with data-quality expectations.
3. Scores only contacts absent from the sentiment table.
4. Publishes the metric view.
5. Registers assets in the Contact Centre domain and configures Genie instructions.

Use a distinct batch label for an incremental drop:

```bash
databricks bundle run -t dev connect_transcript_sentiment_job \
  --params contacts=20,batch_label=second-drop
```

## Use real Amazon Connect exports

Contact Lens can export post-call analytics JSON to Amazon S3. Point Auto Loader at a Unity
Catalog external location over the export path, or schedule a copy into an ADLS-backed volume.
Keep the `connect/Analysis/Voice` path and Contact Lens JSON shape unchanged. Review redaction,
retention, private connectivity and inference-table access before using real transcripts.

The scoring anti-join limits model calls to new contact IDs. Avoid pipeline full refreshes unless
the transformation has changed: a refresh rebuilds pipeline tables, while the sentiment MERGE
still preserves already-scored contact IDs.

## 5. Validate

```bash
uvx ruff check .
uvx ruff format --check .
pytest -q
databricks bundle validate -t dev
```

Then verify that:

- planted invalid rows were dropped from silver;
- every non-NULL sentiment is one of the four contract labels;
- closing-label agreement on synthetic data is at least 85 percent;
- a rerun with the same batch scores no new contacts;
- the model endpoint is back at zero model units;
- Genie can answer contact count, negative-share and queue questions from the metric view.

## Production controls

Production jobs run as the runtime service principal. Bundle production mode makes deployed
resource configuration read-only in the UI, so changes go through Git, pull-request checks and
the deployment workflow. Keep workspace-specific values in target overrides and secrets outside
the repository.

The Unity AI Gateway model service is the governed inference entry point. Use
`notebooks/04_gateway_observability.py` to inspect calls, tokens, latency, errors and request
tags in `system.ai_gateway.usage`. Restrict access to the inference payload table because it can
contain transcript text.

The governance task assigns the silver tables, metric view and Genie space to the
`Customer Experience > Contact Centre` domain. Make semantic changes in a workspace Git folder,
create a branch and pull request, and let CI validate and deploy the bundle rather than editing
production resources in place.
