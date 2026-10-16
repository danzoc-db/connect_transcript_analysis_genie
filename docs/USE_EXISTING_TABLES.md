# Use existing bronze and silver tables

The demo lands synthetic Contact Lens JSON in a volume and builds its own bronze and silver
tables. If your lakehouse already ingests Amazon Connect transcripts into Unity Catalog, skip
those steps and point the scoring stage at the tables you already have. Everything from
sentiment scoring onward (Unity AI Gateway, metric view, Genie, domain) stays the same.

```text
Demo:      synthetic JSON -> volume -> bronze -> silver -> score -> metric view -> Genie
Existing:  your bronze/silver (Unity Catalog) -> contract view -> score -> metric view -> Genie
```

## 1. Check what you already have

Answer these before changing anything. They decide which path below applies.

| Question | Why it matters |
| --- | --- |
| Are the tables in Unity Catalog, not `hive_metastore`? | Serverless jobs, the model service and Genie need Unity Catalog tables. |
| Is bronze still the raw Contact Lens JSON shape (`CustomerMetadata`, `Transcript[]`, `ContactAttributes`)? | If yes, the demo silver SQL works with a one-line change (path A). |
| Is silver one row per contact, or one row per transcript turn? | Turn-level silver must be aggregated to one row per contact (path B). |
| How is silver written: append-only, MERGE, or full overwrite (for example dbt `table` materialization)? | Streaming reads fail on overwrites and updates. Use a view or materialized view instead. |
| Is the transcript text redacted by Contact Lens or downstream? | The scoring prompt and the gateway inference table will contain this text. |
| Which columns hold queue, contact reason, agent, hold time, transfer flag and duration? | These feed the metric-view dimensions and measures. |

## 2. The contract the scoring stage needs

`notebooks/02_score_sentiment.py` reads one table and expects one row per contact with these
columns. Everything else in the row is copied into the sentiment table and is optional.

| Column | Type | Required by |
| --- | --- | --- |
| `contact_id` | STRING, unique | Scoring anti-join and MERGE key |
| `customer_text` | STRING | Overall sentiment |
| `customer_opening_text` | STRING | Opening sentiment |
| `customer_mid_text` | STRING, nullable | Mid-call sentiment |
| `customer_closing_text` | STRING | Closing sentiment and trajectory |
| `contact_date` | DATE | Metric-view time dimensions |
| `queue`, `contact_reason`, `agent_name` | STRING | Metric-view dimensions |
| `hold_seconds`, `duration_seconds`, `transferred` | INT, DOUBLE, BOOLEAN | Handling measures |

`county` and `segment` are synthetic demo dimensions. Map them to real columns or remove them
from the metric view.

Use only customer turns in the four text columns. Agent speech would skew the sentiment.

## 3. Choose a path

### Path A: bronze is raw Contact Lens JSON

Keep the demo silver logic and read from your bronze table instead of the demo one.

1. Delete `pipelines/01_bronze_transcripts.sql` and remove it from `resources/pipeline.yml`.
2. In `pipelines/02_silver_transcripts.sql`, replace
   `FROM STREAM(bronze_connect_transcripts)` with your table, passed as configuration:

   ```sql
   FROM STREAM(${source_bronze_table})
   ```

   ```yaml
   # resources/pipeline.yml
   configuration:
     source_bronze_table: your_catalog.your_schema.your_contact_lens_bronze
   ```

3. If your bronze columns differ from the demo (for example `_metadata` fields renamed, or
   `source_file` and `ingested_at` absent), adjust the `ordered` CTE column list.
4. Update the `known_queue` expectation to your real queue names.
5. If bronze is overwritten rather than appended, change the silver table to
   `CREATE OR REFRESH MATERIALIZED VIEW` and remove `STREAM(...)`.

### Path B: silver is already cleansed

Skip the pipeline entirely and publish a thin view that maps your silver onto the contract.

1. Remove `resources/pipeline.yml`, both files in `pipelines/`, and the `refresh_pipeline` task
   in `resources/job.yml`.
2. Add `sql/silver_connect_transcripts.sql` that creates the contract view in the demo schema.
   For turn-level silver, aggregate customer turns per contact:

   ```sql
   USE CATALOG IDENTIFIER(:catalog);
   USE SCHEMA IDENTIFIER(:schema);

   CREATE OR REPLACE VIEW silver_connect_transcripts AS
   WITH customer_turns AS (
     SELECT
       contact_id,
       array_sort(
         collect_list(named_struct('offset', begin_offset_ms, 'text', content))
       ).text AS lines
     FROM your_catalog.your_schema.your_connect_transcript_turns
     WHERE participant_role = 'CUSTOMER'
     GROUP BY contact_id
   )
   SELECT
     c.contact_id,
     CAST(c.initiation_ts AS DATE) AS contact_date,
     c.queue_name AS queue,
     c.contact_reason,
     c.agent_name,
     c.hold_duration_seconds AS hold_seconds,
     c.is_transferred AS transferred,
     c.duration_seconds,
     array_join(t.lines, ' ') AS customer_text,
     element_at(t.lines, 1) AS customer_opening_text,
     CASE WHEN size(t.lines) >= 3
       THEN array_join(slice(t.lines, 2, size(t.lines) - 2), ' ')
     END AS customer_mid_text,
     element_at(t.lines, -1) AS customer_closing_text
   FROM your_catalog.your_schema.your_connect_contacts c
   INNER JOIN customer_turns t USING (contact_id)
   WHERE c.contact_id IS NOT NULL;
   ```

   Replace every `your_*` name and column with your own. Drop or replicate the demo filters you
   still need (completed analysis only, plausible duration, sign-off lines removed).
3. Add a `publish_contract_view` SQL task before `score_sentiment` in `resources/job.yml`,
   using the same pattern as `publish_metric_view`.

The contract table name `silver_connect_transcripts` is kept so the scoring notebook needs no
rename. To read your silver table directly instead, change `silver_table` in
`notebooks/02_score_sentiment.py` and make sure the column names already match the contract.

## 4. Changes common to both paths

### Job (`resources/job.yml`)

- Remove the `land_transcripts` task. It writes synthetic data only.
- Remove the `contacts` and `batch_label` job parameters.
- Point `score_sentiment` at the new upstream task (`refresh_pipeline` in path A,
  `publish_contract_view` in path B).
- Unpause the schedule once a run succeeds, aligned to when your silver refreshes.

### Schema and volume (`resources/schema.yml`)

- Delete the `raw_transcripts` volume.
- Keep the analytics schema. Scoring output, the metric view and the inference table still
  live there, separate from the source tables.

### Scoring notebook (`notebooks/02_score_sentiment.py`)

- Remove the agreement check that joins `bronze_connect_transcripts` on
  `ContactAttributes.QaArcLabel`. That hidden label exists only in synthetic data, and the join
  fails when the demo bronze table does not exist. Replace it with a manual sample review of
  scored real calls.
- The first run scores the whole history. Size it first with
  `SELECT COUNT(*) FROM silver_connect_transcripts`, or add a `WHERE contact_date >= ...`
  backfill window to the anti-join query, then widen it.

### Metric view (`sql/contact_sentiment_metrics.sql`)

- Remove or remap dimensions with no real source (`county`, `segment`).
- Keep the measures. They depend only on the contract columns.

### Domain and grants (`notebooks/03_register_domain_assets.py`)

- Remove `bronze_connect_transcripts` and `silver_connect_transcripts` from the tagging loop if
  they are not created in the demo schema. Tag source tables only if their owner agrees; it
  needs `APPLY_TAG` on tables you may not own.
- Update the Genie sample questions and example SQL to real queue names (the demo uses
  `Billing`).

### Permissions

Grant the runtime service principal read access to the source tables:

```sql
GRANT USE CATALOG ON CATALOG your_catalog TO `<runtime-application-id>`;
GRANT USE SCHEMA ON SCHEMA your_catalog.your_schema TO `<runtime-application-id>`;
GRANT SELECT ON TABLE your_catalog.your_schema.<each source table> TO `<runtime-application-id>`;
```

Analysts still need only `SELECT` on `silver_transcript_sentiment` and
`contact_sentiment_metrics` in the analytics schema, not on the source tables.

### Bundle variables (`databricks.yml`)

- Add a variable for each source table name so dev and prod can point at different
  environments, and reference it from the pipeline configuration or the contract-view task.
- Set `catalog`, `schema`, `warehouse_id` and the service principals for your workspace.

### Tests

- `tests/test_pipeline_contract.py` asserts the demo bronze and silver SQL. Replace those tests
  with checks on your contract view or silver SQL.
- `tests/test_bundle_contract.py` expects `volumes:` and `pipelines:`. Update it to match the
  resources you keep.
- Skip `tests/test_generator.py` and the synthetic generator if you no longer run it.

## 5. Before using real transcripts

- Confirm the model is in-geography for your workspace region (see
  [Getting started](GETTING_STARTED.md#data-residency-and-model-choice)).
- Restrict access to the gateway inference table. It stores request payloads, which contain
  transcript text.
- Use redacted transcripts wherever possible.
- Agree retention for the sentiment table and the inference table.

## 6. Validate

- Every non-NULL sentiment is `positive`, `negative`, `neutral` or `mixed`.
- A rerun with no new source rows scores zero contacts.
- The endpoint returns to zero model units after each run.
- Genie answers queue and negative-share questions from the metric view.
- A sample of real calls, reviewed by the contact-centre team, agrees with the closing
  sentiment.
