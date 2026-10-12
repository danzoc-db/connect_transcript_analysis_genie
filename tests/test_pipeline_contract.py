"""Offline contract checks for the pipeline and bundle."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bronze_uses_auto_loader_streaming_from_volume():
    sql = (ROOT / "pipelines" / "01_bronze_transcripts.sql").read_text()
    assert "CREATE OR REFRESH STREAMING TABLE bronze_connect_transcripts" in sql
    assert "STREAM read_files(" in sql
    assert "${volume_path}/connect/Analysis/Voice" in sql
    assert "_metadata.file_path AS source_file" in sql


def test_silver_has_drop_and_warning_expectations():
    sql = (ROOT / "pipelines" / "02_silver_transcripts.sql").read_text()
    for required in (
        "valid_contact_id",
        "has_customer_turns",
        "completed_job",
        "known_queue",
        "plausible_duration",
    ):
        assert f"CONSTRAINT {required} EXPECT" in sql
    assert "valid_contact_id EXPECT" in sql and "ON VIOLATION DROP ROW" in sql
    assert "has_customer_turns EXPECT" in sql and "ON VIOLATION DROP ROW" in sql
    assert "completed_job EXPECT" in sql and "ON VIOLATION DROP ROW" in sql


def test_silver_excludes_hidden_ground_truth_and_builds_temporal_windows():
    sql = (ROOT / "pipelines" / "02_silver_transcripts.sql").read_text()
    selected = sql.split("SELECT", 1)[-1]
    assert "QaArcLabel AS" not in selected
    assert "substantive_customer_lines" in sql
    assert "No, that is everything. Goodbye." in sql
    assert "element_at(substantive_customer_lines, 1)" in sql
    assert "element_at(substantive_customer_lines, -1)" in sql
    for column in (
        "customer_text",
        "customer_opening_text",
        "customer_mid_text",
        "customer_closing_text",
    ):
        assert column in sql


def test_sentiment_is_not_scored_inside_pipeline():
    pipeline = "\n".join(path.read_text() for path in (ROOT / "pipelines").glob("*.sql"))
    assert "ai_analyze_sentiment(" not in pipeline
    assert "ai_query(" not in pipeline


def test_scoring_job_enforces_hidden_label_quality_target():
    notebook = (ROOT / "notebooks" / "02_score_sentiment.py").read_text()
    assert "scored.sentiment_closing = raw.ContactAttributes.QaArcLabel" in notebook
    assert "agreement < 0.85" in notebook


def test_domain_task_grants_analysts_only_semantic_layer_access():
    notebook = (ROOT / "notebooks" / "03_register_domain_assets.py").read_text()
    assert "GRANT USE CATALOG" in notebook
    assert "GRANT USE SCHEMA" in notebook
    assert '("silver_transcript_sentiment", "contact_sentiment_metrics")' in notebook
    assert "bronze_connect_transcripts" not in notebook.split(
        "def grant_analyst_access", 1
    )[1].split("for asset in (", 1)[0]
