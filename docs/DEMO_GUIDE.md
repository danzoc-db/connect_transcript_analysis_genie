# Demo Guide

## Story

Contact Lens JSON lands in a governed volume. A Lakeflow pipeline applies expectations and
creates one clean row per call. A Python task scores customer-only sentiment through a Unity AI
Gateway model service, capturing opening, middle, closing and overall sentiment. A Unity Catalog
metric view supplies consistent measures to Genie.

## Before presenting

1. Run the end-to-end job with at least 60 contacts.
2. Confirm bronze has three more rows than silver because of the planted defects.
3. Confirm the hidden closing-label agreement is at least 85 percent.
4. Confirm the endpoint is parked at zero model units.
5. Ask Genie:
   - How many contacts were handled?
   - Which queues have the highest negative share?
   - Compare opening and closing sentiment by queue.
6. Open the Git folder and the metric-view SQL file.

Use `notebooks/04_gateway_observability.py` to show request volume, tokens, latency, errors and
sample synthetic payloads recorded by Unity AI Gateway.

## Live change

Follow [LIVE_DEMO_CHANGE.md](LIVE_DEMO_CHANGE.md). Uncomment only the
`sentiment_recovery_rate` measure, create a branch, open a pull request, and show the checks.
After deployment, ask Genie:

```text
What is our sentiment recovery rate by queue this month?
```

The point is not only that Genie answers. The KPI has one reviewed definition, is deployed as
code, and is reused by SQL and Genie.

## Useful verification SQL

```sql
SELECT
  MEASURE(total_contacts),
  MEASURE(negative_share),
  MEASURE(net_sentiment_score)
FROM contact_centre_analytics.connect_analytics_dev.contact_sentiment_metrics;
```

```sql
SELECT
  queue,
  MEASURE(total_contacts),
  MEASURE(negative_share)
FROM contact_centre_analytics.connect_analytics_dev.contact_sentiment_metrics
GROUP BY queue
ORDER BY MEASURE(negative_share) DESC;
```

## Recovery

- If scoring fails, verify the model service rate limit and endpoint status, then rerun. The
  anti-join prevents successful contacts from being rescored.
- If a run fails before scoring begins, park the endpoint explicitly:
  `uv run python scripts/manage_pt_endpoint.py --profile your-profile --units 0`.
- If the metric view fails, test its YAML in the SQL editor and keep YAML values containing a
  colon in double quotes.
