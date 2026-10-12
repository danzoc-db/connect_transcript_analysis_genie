# Demo Architecture

```text
Amazon Connect Contact Lens JSON
                 |
                 v
Unity Catalog volume: raw_transcripts
                 |
                 v
Lakeflow pipeline
  bronze_connect_transcripts
          |
          v
  silver_connect_transcripts
  - drop invalid ID, failed job, no customer speech
  - warn on queue and duration anomalies
                 |
                 v
Serverless scoring task
  - anti-join on contact_id
  - opening, middle, closing, overall customer sentiment
  - bounded concurrency and 429/503 retry
                 |
                 v
Unity AI Gateway model service
  - EXECUTE governance
  - 600 requests per minute
  - usage and inference tables
                 |
                 v
gpt-oss-20b provisioned-throughput endpoint
  - 50 model units while scoring
  - 0 model units while parked
                 |
                 v
silver_transcript_sentiment
                 |
                 v
Materialized Unity Catalog metric view
                 |
                 v
Genie space
```

Databricks Asset Bundles manage the schema, volume, pipeline, job, model service and Genie
space. The PT endpoint is the sole exception because the current bundle provider uses the
classic update API rather than the required model-unit PT API. GitHub Actions validates pull
requests and deploys the production target.

The domain hierarchy is `Customer Experience > Contact Centre`. The governance task assigns
the bronze table, silver table, sentiment table, metric view and Genie space to its governed
tag.
