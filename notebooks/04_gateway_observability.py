# Databricks notebook source
"""Operational checks for Unity AI Gateway and the transcript model service."""

# COMMAND ----------

dbutils.widgets.text("catalog", "contact_centre_analytics")
dbutils.widgets.text("schema", "connect_analytics_dev")
dbutils.widgets.text("lookback_days", "7")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
lookback_days = int(dbutils.widgets.get("lookback_days"))
service_name = f"{catalog}.{schema}.transcript_sentiment"

# COMMAND ----------

usage = spark.sql(
    f"""
    SELECT
      DATE(event_time) AS event_date,
      requester,
      requester_type,
      invocation_metadata.source AS invocation_source,
      destination_name,
      COUNT(*) AS calls,
      SUM(total_tokens) AS tokens,
      PERCENTILE_APPROX(latency_ms, 0.50) AS p50_latency_ms,
      PERCENTILE_APPROX(latency_ms, 0.95) AS p95_latency_ms,
      COUNT_IF(status_code >= 400) / COUNT(*) AS error_rate
    FROM system.ai_gateway.usage
    WHERE service_name = '{service_name}'
      AND event_time >= CURRENT_TIMESTAMP() - INTERVAL {lookback_days} DAYS
    GROUP BY ALL
    ORDER BY event_date DESC, calls DESC
    """
)
display(usage)

# COMMAND ----------

status_codes = spark.sql(
    f"""
    SELECT
      status_code,
      destination_name,
      COUNT(*) AS calls,
      MIN(event_time) AS first_seen,
      MAX(event_time) AS last_seen
    FROM system.ai_gateway.usage
    WHERE service_name = '{service_name}'
      AND event_time >= CURRENT_TIMESTAMP() - INTERVAL {lookback_days} DAYS
    GROUP BY ALL
    ORDER BY calls DESC
    """
)
display(status_codes)

# COMMAND ----------

# Payloads contain synthetic customer text in this demo. Apply production retention,
# redaction and access policies before enabling payload logging for real transcripts.
payload_samples = spark.sql(
    f"""
    SELECT
      event_time,
      request_id,
      status_code,
      latency_ms,
      destination_name,
      request,
      response
    FROM `{catalog}`.`{schema}`.`transcript_sentiment_payload`
    ORDER BY event_time DESC
    LIMIT 3
    """
)
display(payload_samples)
