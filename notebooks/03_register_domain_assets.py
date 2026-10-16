# Databricks notebook source
"""Idempotently assign pipeline, metric-view and Genie assets to the domain."""

import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import AlreadyExists

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("genie_space_id", "")
dbutils.widgets.text("domain_tag_key", "customer_experience/Contact Centre")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
genie_space_id = dbutils.widgets.get("genie_space_id")
tag_key = dbutils.widgets.get("domain_tag_key")
w = WorkspaceClient()


def configure_genie(space_id: str) -> None:
    """Attach the metric view, drill table, instructions and benchmark SQL."""
    response = w.api_client.do(
        "GET",
        f"/api/2.0/genie/spaces/{space_id}",
        query={"include_serialized_space": "true"},
    )
    serialized = json.loads(response.get("serialized_space") or '{"version":2}')
    serialized["data_sources"] = {
        "tables": [
            {"identifier": f"{catalog}.{schema}.silver_transcript_sentiment"},
        ],
        "metric_views": [
            {"identifier": f"{catalog}.{schema}.contact_sentiment_metrics"},
        ],
    }
    serialized.setdefault("config", {})["sample_questions"] = [
        {
            "id": "41111111111111111111111111111111",
            "question": ["Which queue had the highest negative share?"],
        },
        {
            "id": "42222222222222222222222222222222",
            "question": ["Compare opening and closing sentiment by queue."],
        },
    ]
    instruction_id = "11111111111111111111111111111111"
    serialized["instructions"] = {
        "text_instructions": [
            {
                "id": instruction_id,
                "content": [
                    "Use contact_sentiment_metrics for KPI questions.\n",
                    "Sentiment is positive, negative, neutral, mixed, or NULL.\n",
                    "Negative share is negative contacts divided by scored contacts.\n",
                    "Weeks start on Monday.\n",
                    "Use silver_transcript_sentiment only for contact-level drill-down.\n",
                    "Do not expose full transcripts unless the user explicitly asks.\n",
                ],
            }
        ],
        "example_question_sqls": [
            {
                "id": "21111111111111111111111111111111",
                "question": ["Which queue had the highest negative share?"],
                "sql": [
                    f"SELECT queue, MEASURE(negative_share) AS negative_share "
                    f"FROM {catalog}.{schema}.contact_sentiment_metrics "
                    "GROUP BY ALL ORDER BY negative_share DESC LIMIT 1"
                ],
                "parameters": [],
                "usage_guidance": [],
            },
            {
                "id": "22222222222222222222222222222222",
                "question": ["Show net sentiment score by week for Billing."],
                "sql": [
                    f"SELECT contact_week, MEASURE(net_sentiment_score) AS net_sentiment_score "
                    f"FROM {catalog}.{schema}.contact_sentiment_metrics "
                    "WHERE queue = 'Billing' GROUP BY ALL ORDER BY contact_week"
                ],
                "parameters": [],
                "usage_guidance": [],
            },
        ],
    }
    serialized["benchmarks"] = {
        "questions": [
            {
                "id": "31111111111111111111111111111111",
                "question": ["Which queue had the highest negative share?"],
                "answer": [
                    {
                        "format": "SQL",
                        "content": [
                            f"SELECT queue, MEASURE(negative_share) AS negative_share "
                            f"FROM {catalog}.{schema}.contact_sentiment_metrics "
                            "GROUP BY ALL ORDER BY negative_share DESC LIMIT 1"
                        ],
                    }
                ],
            },
            {
                "id": "32222222222222222222222222222222",
                "question": ["Show net sentiment score by week for Billing."],
                "answer": [
                    {
                        "format": "SQL",
                        "content": [
                            "SELECT contact_week, "
                            "MEASURE(net_sentiment_score) AS net_sentiment_score "
                            f"FROM {catalog}.{schema}.contact_sentiment_metrics "
                            "WHERE queue = 'Billing' GROUP BY ALL ORDER BY contact_week"
                        ],
                    }
                ],
            },
        ]
    }
    w.api_client.do(
        "PATCH",
        f"/api/2.0/genie/spaces/{space_id}",
        body={"serialized_space": json.dumps(serialized)},
    )
    print(f"Configured Genie space: {space_id}")


def ensure_uc_tag(full_name: str) -> None:
    try:
        w.api_client.do(
            "POST",
            "/api/2.1/unity-catalog/entity-tag-assignments",
            body={
                "entity_name": full_name,
                "entity_type": "tables",
                "tag_key": tag_key,
            },
        )
        print(f"Tagged: {full_name}")
    except AlreadyExists:
        print(f"Already tagged: {full_name}")


def quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def grant_analyst_access() -> None:
    catalog_id = quote_identifier(catalog)
    schema_id = quote_identifier(schema)
    analyst_group = quote_identifier("contact_centre_analysts")
    spark.sql(f"GRANT USE CATALOG ON CATALOG {catalog_id} TO {analyst_group}")
    spark.sql(f"GRANT USE SCHEMA ON SCHEMA {catalog_id}.{schema_id} TO {analyst_group}")
    for asset in ("silver_transcript_sentiment", "contact_sentiment_metrics"):
        asset_id = quote_identifier(asset)
        spark.sql(f"GRANT SELECT ON TABLE {catalog_id}.{schema_id}.{asset_id} TO {analyst_group}")
    print("Granted analyst access to the governed semantic layer")


for asset in (
    "bronze_connect_transcripts",
    "silver_connect_transcripts",
    "silver_transcript_sentiment",
    "contact_sentiment_metrics",
):
    ensure_uc_tag(f"{catalog}.{schema}.{asset}")

grant_analyst_access()

if genie_space_id:
    configure_genie(genie_space_id)
    try:
        w.api_client.do(
            "POST",
            "/api/2.0/entity-tag-assignments",
            body={
                "entity_type": "geniespaces",
                "entity_id": genie_space_id,
                "tag_key": tag_key,
            },
        )
        print(f"Tagged Genie space: {genie_space_id}")
    except AlreadyExists:
        print(f"Genie space already tagged: {genie_space_id}")
