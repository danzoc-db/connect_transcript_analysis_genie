# Connect Transcript Analysis + Genie

> **Synthetic data disclaimer.** Every transcript, name, region, amount and identifier in this
> repository is synthetically generated at runtime by `src/connect_sentiment/generator.py`.
> "Northwind Energy" is a fictional company. This repository contains no real customer,
> employee or personal data, is not connected to any customer system or Databricks workspace,
> and does not describe any real organisation's environment.

This public Databricks demo turns synthetic Amazon Connect Contact Lens transcripts into
governed contact-centre insights that analysts can query in natural language.

## Architecture

```text
Synthetic Contact Lens JSON
            |
            v
Unity Catalog volume
            |
            v
Lakeflow Spark Declarative Pipeline
  bronze_transcripts -> silver_transcripts
            |
            v
Python scoring task -> Unity AI Gateway model service
                    -> gpt-oss-20b PT endpoint
            |
            v
transcript_sentiment Delta table
            |
            v
Unity Catalog metric view -> Genie space
```

The pipeline uses expectations to drop unusable contacts and retain warnings for suspicious
records. The scoring task analyzes customer speech over early, middle, late and overall windows,
then incrementally MERGEs one result per contact. The endpoint is raised to 50 provisioned model
units only while scoring and parked at zero afterward.

## Highlights

- Databricks Asset Bundles deploy the schema, volume, pipeline, job and Genie space.
- A Unity AI Gateway model service governs every inference request.
- The sentiment contract is `positive`, `negative`, `neutral`, `mixed` or NULL.
- Unity Catalog domains group the silver tables, sentiment table, metric view and Genie space.
- Offline tests cover coherent data generation, scoring behavior, data-quality expectations and
  bundle contracts.
- GitHub Actions runs offline lint and tests on pull requests. A deploy workflow template for
  your own private fork is in `templates/github-actions/`.

## Quick start

See [Getting started](docs/GETTING_STARTED.md). The design rationale is in
[Architecture decisions](docs/architecture-decisions.md), and the presenter workflow is in
[Demo guide](docs/DEMO_GUIDE.md).

## Data privacy

- All data is synthetic and generated at runtime; no dataset is stored in this repository.
- Generated records carry a `ContactAttributes.DataNotice` field, and every table, volume,
  metric view and Genie space created by the bundle is labelled as synthetic.
- Do not load real recordings or transcripts into a deployment of this demo. If you adapt it
  for real data, apply your own data-protection assessment, access controls and retention
  rules first (see [Using existing tables](docs/USE_EXISTING_TABLES.md)).
