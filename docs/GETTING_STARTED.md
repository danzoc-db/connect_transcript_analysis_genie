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

This public repository is not wired to any workspace. `databricks.yml` contains no profile,
host, warehouse ID or service principal ID. Set `catalog` and `schema` in the `dev` and `prod`
overrides if needed, and supply the workspace-specific values at deploy time:

- `warehouse_id`
- `runtime_service_principal_name`
- `deploy_service_principal_name`

Use `BUNDLE_VAR_<name>` environment variables, `--var <name>=<value>`, or the gitignored
`.databricks/bundle/<target>/variable-overrides.json`. Never commit these values to a public
repository.

Authenticate with your own CLI profile and verify the target:

```bash
databricks auth login --host https://your-workspace-host --profile your-profile
export DATABRICKS_CONFIG_PROFILE=your-profile
export BUNDLE_VAR_warehouse_id=<warehouse-id>
export BUNDLE_VAR_runtime_service_principal_name=<runtime-sp-application-id>
export BUNDLE_VAR_deploy_service_principal_name=<deploy-sp-application-id>
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

### Optional: deploy from GitHub Actions

The public CI in this repository runs offline lint and tests only. To deploy from GitHub, use a
**private fork** and copy `templates/github-actions/deploy.yml.template` to
`.github/workflows/deploy.yml`. The template uses GitHub OIDC workload identity federation, so
no client secret is stored. Configure a Databricks federation policy for your repository and set
these repository variables for your own workspace:

```text
Variable: DATABRICKS_HOST
Variable: DATABRICKS_CLIENT_ID
Variable: DATABRICKS_RUNTIME_CLIENT_ID
Variable: DATABRICKS_WAREHOUSE_ID
```

Add a required-reviewer protection rule to the `production` environment. If the workspace
enforces an IP access list, register a self-hosted runner on an allowed network and set the
repository variable `DATABRICKS_RUNNER` to its runner label.

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

If Amazon Connect transcripts are already in bronze or silver tables in your lakehouse, skip
landing and ingestion. See [Use existing bronze and silver tables](USE_EXISTING_TABLES.md).

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
create a branch and pull request, and let CI validate the change before you deploy the bundle,
rather than editing production resources in place.
