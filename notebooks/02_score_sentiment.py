# Databricks notebook source
"""Score only new contacts through the Unity AI Gateway model service."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk import WorkspaceClient
from pyspark.sql import types as T


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parents[1]
    except NameError:
        notebook_path = (
            dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        )
        return (Path("/Workspace") / notebook_path.lstrip("/")).parents[1]


sys.path.insert(0, str(_project_root() / "src"))

from connect_sentiment.scoring import (
    RetryableGatewayError,
    build_sentiment_request,
    derive_trajectory,
    score_with_retry,
)

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("model_service", "")
dbutils.widgets.text("endpoint_name", "")
dbutils.widgets.text("model_units", "50")
dbutils.widgets.text("max_workers", "8")
dbutils.widgets.text("job_id", "")
dbutils.widgets.text("job_run_id", "")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
model_service = dbutils.widgets.get("model_service")
endpoint_name = dbutils.widgets.get("endpoint_name")
model_units = int(dbutils.widgets.get("model_units"))
max_workers = int(dbutils.widgets.get("max_workers"))
job_id = dbutils.widgets.get("job_id")
job_run_id = dbutils.widgets.get("job_run_id")

silver_table = f"`{catalog}`.`{schema}`.`silver_connect_transcripts`"
sentiment_table = f"`{catalog}`.`{schema}`.`silver_transcript_sentiment`"

w = WorkspaceClient()
host = w.config.host.rstrip("/")
auth_headers = {
    **w.config.authenticate(),
    "Content-Type": "application/json",
    "Databricks-Ai-Gateway-Request-Tags": json.dumps(
        {
            "project": "connect_transcript_analysis_genie",
            "job_id": job_id,
            "job_run_id": job_run_id,
            "task": "score_sentiment",
        }
    ),
}


def set_model_units(units: int) -> None:
    """Preserve the live entity identity while changing model-unit capacity."""
    endpoint = w.api_client.do("GET", f"/api/2.0/serving-endpoints/{endpoint_name}")
    entity = endpoint["config"]["served_entities"][0]
    body = {
        "config": {
            "served_entities": [
                {
                    "name": entity["name"],
                    "entity_name": entity["entity_name"],
                    "entity_version": entity["entity_version"],
                    "provisioned_model_units": units,
                }
            ]
        }
    }
    w.api_client.do(
        "PUT",
        f"/api/2.0/serving-endpoints/pt/{endpoint_name}/config",
        body=body,
    )
    print(f"Set {endpoint_name} provisioned_model_units={units}")


def send_gateway(request_body):
    request = urllib.request.Request(
        host + "/ai-gateway/mlflow/v1/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers=auth_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", "replace")
        if exc.code in {429, 503}:
            raise RetryableGatewayError(exc.code, message) from exc
        raise RuntimeError(f"gateway HTTP {exc.code}: {message}") from exc


spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {sentiment_table}
    COMMENT 'Synthetic demo data: contact sentiment via Unity AI Gateway. No real personal data.'
    AS
    SELECT
      s.*,
      CAST(NULL AS STRING) AS sentiment,
      CAST(NULL AS STRING) AS sentiment_opening,
      CAST(NULL AS STRING) AS sentiment_mid,
      CAST(NULL AS STRING) AS sentiment_closing,
      CAST(NULL AS STRING) AS sentiment_shift,
      CAST(NULL AS STRING) AS sentiment_path,
      CAST(NULL AS STRING) AS sentiment_model,
      CAST(NULL AS STRING) AS sentiment_service,
      CAST(NULL AS TIMESTAMP) AS scored_at,
      CAST(NULL AS STRING) AS sentiment_error
    FROM {silver_table} s
    WHERE false
    """
)

new_contacts = [
    row.asDict(recursive=True)
    for row in spark.sql(
        f"""
        SELECT s.*
        FROM {silver_table} s
        LEFT ANTI JOIN {sentiment_table} t
          ON s.contact_id = t.contact_id
        """
    ).collect()
]

print(f"New contacts to score: {len(new_contacts)}")
if not new_contacts:
    current = w.api_client.do("GET", f"/api/2.0/serving-endpoints/{endpoint_name}")
    current_units = current["config"]["served_entities"][0]["provisioned_model_units"]
    if current_units != 0:
        set_model_units(0)
    dbutils.notebook.exit("No new contacts; endpoint parked at 0 PMU.")

set_model_units(model_units)
windows = {
    "sentiment": "customer_text",
    "sentiment_opening": "customer_opening_text",
    "sentiment_mid": "customer_mid_text",
    "sentiment_closing": "customer_closing_text",
}
scores: dict[str, dict[str, object]] = {
    row["contact_id"]: {"contact_id": row["contact_id"], "errors": []} for row in new_contacts
}

try:
    futures = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for row in new_contacts:
            for output_column, input_column in windows.items():
                text = row.get(input_column)
                if not text:
                    scores[row["contact_id"]][output_column] = None
                    continue
                future = executor.submit(
                    score_with_retry,
                    send_gateway,
                    build_sentiment_request(model_service, text),
                )
                futures[future] = (row["contact_id"], output_column)

        for future in as_completed(futures):
            contact_id, output_column = futures[future]
            result = future.result()
            scores[contact_id][output_column] = result.sentiment
            if result.model:
                scores[contact_id]["sentiment_model"] = result.model
            if result.error:
                scores[contact_id]["errors"].append(f"{output_column}: {result.error}")

    output_rows = []
    scored_at = datetime.now(UTC).replace(tzinfo=None)
    for contact_id, values in scores.items():
        trajectory = derive_trajectory(
            values.get("sentiment_opening"),
            values.get("sentiment_mid"),
            values.get("sentiment_closing"),
        )
        output_rows.append(
            (
                contact_id,
                values.get("sentiment"),
                values.get("sentiment_opening"),
                values.get("sentiment_mid"),
                values.get("sentiment_closing"),
                trajectory.shift,
                trajectory.path,
                values.get("sentiment_model"),
                model_service,
                scored_at,
                "; ".join(values["errors"]) or None,
            )
        )

    result_schema = T.StructType(
        [
            T.StructField("contact_id", T.StringType(), False),
            T.StructField("sentiment", T.StringType()),
            T.StructField("sentiment_opening", T.StringType()),
            T.StructField("sentiment_mid", T.StringType()),
            T.StructField("sentiment_closing", T.StringType()),
            T.StructField("sentiment_shift", T.StringType()),
            T.StructField("sentiment_path", T.StringType()),
            T.StructField("sentiment_model", T.StringType()),
            T.StructField("sentiment_service", T.StringType()),
            T.StructField("scored_at", T.TimestampType()),
            T.StructField("sentiment_error", T.StringType()),
        ]
    )
    spark.createDataFrame(output_rows, result_schema).createOrReplaceTempView("_sentiment_results")

    spark.sql(
        f"""
        MERGE INTO {sentiment_table} target
        USING (
          SELECT s.*, r.* EXCEPT (contact_id)
          FROM {silver_table} s
          INNER JOIN _sentiment_results r USING (contact_id)
        ) source
        ON target.contact_id = source.contact_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )

    quality = spark.sql(
        f"""
        SELECT
          COUNT(*) AS evaluated_contacts,
          AVG(
            CASE
              WHEN scored.sentiment_closing = raw.ContactAttributes.QaArcLabel THEN 1.0
              ELSE 0.0
            END
          ) AS agreement
        FROM {sentiment_table} scored
        INNER JOIN `{catalog}`.`{schema}`.`bronze_connect_transcripts` raw
          ON scored.contact_id = raw.CustomerMetadata.ContactId
        WHERE raw.ContactAttributes.QaArcLabel IS NOT NULL
        """
    ).first()
    agreement = quality["agreement"]
    if quality["evaluated_contacts"]:
        print(f"Closing-sentiment agreement with hidden QA arc: {agreement:.1%}")
        if agreement < 0.85:
            raise RuntimeError(f"Sentiment agreement {agreement:.1%} is below the 85% target")
    else:
        print("No hidden QA labels were present; agreement check skipped")
finally:
    set_model_units(0)
