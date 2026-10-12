# Databricks notebook source
"""Presenter helper for the Connect transcript analysis demo."""

# COMMAND ----------

dbutils.widgets.text("catalog", "contact_centre_analytics")
dbutils.widgets.text("schema", "connect_analytics_dev")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          MEASURE(total_contacts) AS total_contacts,
          MEASURE(negative_share) AS negative_share,
          MEASURE(net_sentiment_score) AS net_sentiment_score
        FROM `{catalog}`.`{schema}`.`contact_sentiment_metrics`
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          queue,
          MEASURE(total_contacts) AS total_contacts,
          MEASURE(negative_share) AS negative_share,
          MEASURE(net_sentiment_score) AS net_sentiment_score
        FROM `{catalog}`.`{schema}`.`contact_sentiment_metrics`
        GROUP BY queue
        ORDER BY negative_share DESC
        """
    )
)

# COMMAND ----------

quality = spark.sql(
    f"""
    SELECT
      COUNT(*) AS scored_contacts,
      COUNT_IF(
        sentiment IS NULL
        OR sentiment NOT IN ('positive', 'negative', 'neutral', 'mixed')
      ) AS invalid_or_null_overall
    FROM `{catalog}`.`{schema}`.`silver_transcript_sentiment`
    """
)
display(quality)

# COMMAND ----------

print("Next:")
print("1. Open the Lakeflow pipeline and show expectation metrics.")
print("2. Open notebooks/04_gateway_observability.py and show gateway usage.")
print("3. Open the Contact Centre Genie space and ask the sample questions.")
print("4. Follow docs/LIVE_DEMO_CHANGE.md for the live KPI pull request.")
