# Production Validation Evidence

Validated on 12 Oct 2026 after a production bundle deployment.

## Orchestration

- Job run `767455700224576`: SUCCESS.
- `land_transcripts`: SUCCESS.
- `refresh_pipeline`: SUCCESS.
- `score_sentiment`: SUCCESS.
- `publish_metric_view`: SUCCESS.
- `register_domain_assets`: SUCCESS.

## Pipeline expectations

The input contained 20 contacts. Bronze retained all 20 and silver retained 17.
The silver flow reported three dropped records:

- `valid_contact_id`: 1 failed, 19 passed.
- `completed_job`: 1 failed, 19 passed.
- `has_customer_turns`: 1 failed, 19 passed.
- `known_queue`: 0 failed, 20 passed.
- `plausible_duration`: 0 failed, 20 passed.

## Sentiment and gateway

- Scored contacts: 17.
- Values outside `positive`, `negative`, `neutral`, and `mixed`: 0.
- Closing-label agreement against the hidden QA arc: 100 percent.
- Model-service inference rows for the run: 68.
- Successful model-service calls: 68.
- Destination: `gpt_oss_20b_pt`.
- Request task tag: `score_sentiment`.
- Endpoint after the run: READY with `provisioned_model_units: 0`.

## Metric view

This query completed successfully:

```sql
SELECT
  queue,
  MEASURE(total_contacts) AS contacts,
  MEASURE(negative_share) AS negative_share,
  MEASURE(net_sentiment_score) AS net_score
FROM contact_centre_analytics.connect_analytics.contact_sentiment_metrics
GROUP BY ALL
ORDER BY contacts DESC;
```

It returned seven queues and 17 contacts. All three Unity Catalog data assets and the
production Genie space had the governed `customer_experience/Contact Centre` domain tag.

## Genie API

All questions completed with generated SQL against the production metric view.

1. `How many contacts are there in total?`
   - Result: 17.
   - SQL used `MEASURE(total_contacts)`.
2. `Which queue has the highest negative sentiment share? Show contact count and negative share for every queue.`
   - Result: Billing and Moving Home were tied at 1.0 for this deterministic 20-contact validation batch.
   - SQL used `MEASURE(total_contacts)` and `MEASURE(negative_share)`.
3. `Compare opening and closing sentiment across all contacts. Show counts by opening sentiment and closing sentiment.`
   - Result: six opening-to-closing combinations across 17 contacts.
   - SQL grouped by `sentiment_opening` and `sentiment_closing` and used `MEASURE(total_contacts)`.
