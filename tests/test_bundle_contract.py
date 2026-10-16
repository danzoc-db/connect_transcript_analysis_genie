"""Static checks for portable bundle configuration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bundle_uses_20b_and_unity_ai_gateway_model_service():
    text = "\n".join(
        path.read_text() for path in [ROOT / "databricks.yml", *(ROOT / "resources").glob("*.yml")]
    )
    assert "system.ai.gpt-oss-20b" in text
    assert "model_services:" in text
    assert "DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL" in text
    assert "ai_gateway:" not in text
    assert "system.ai.gpt-oss-120b" not in text


def test_bundle_has_pipeline_job_volume_and_genie_resources():
    text = "\n".join(
        path.read_text() for path in [ROOT / "databricks.yml", *(ROOT / "resources").glob("*.yml")]
    )
    for resource in ("pipelines:", "jobs:", "volumes:", "genie_spaces:"):
        assert resource in text
    assert "full_refresh: true" not in text


def test_workspace_values_only_appear_in_target_overrides():
    text = (ROOT / "databricks.yml").read_text()
    root, targets = text.split("targets:", 1)
    assert "contact_centre_analytics" not in root
    assert "azsu-centrica-demo" not in root
    assert "contact_centre_analytics" in targets


def test_deploy_identity_retains_management_access():
    bundle = (ROOT / "databricks.yml").read_text()
    schema = (ROOT / "resources" / "schema.yml").read_text()
    access_script = (ROOT / "scripts" / "grant_bundle_file_access.py").read_text()
    assert "deploy_service_principal_name:" in bundle
    assert "${var.deploy_service_principal_name}" in schema
    assert "--pipeline-id" in access_script
    assert "/api/2.0/permissions/pipelines/" in access_script


def test_agent_rule_mirrors_are_identical():
    assert (ROOT / "AGENTS.md").read_text() == (ROOT / ".cursorrules").read_text()


def test_model_unit_endpoint_stays_outside_bundle_state():
    bundle_text = "\n".join(
        path.read_text() for path in [ROOT / "databricks.yml", *(ROOT / "resources").glob("*.yml")]
    )
    assert "model_serving_endpoints:" not in bundle_text
    assert (ROOT / "scripts" / "manage_pt_endpoint.py").exists()


def test_github_workflows_validate_and_deploy_the_bundle():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    deploy = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "ruff check ." in ci
    assert "pytest -q" in ci
    assert "databricks bundle validate -t prod" in ci
    assert "scripts/manage_pt_endpoint.py" in deploy
    assert "--units 0" in deploy
    assert "--runtime-principal" in deploy
    assert "databricks bundle deploy -t prod" in deploy
    assert "scripts/grant_bundle_file_access.py" in deploy
    assert "bundle summary -t prod --output json" in deploy
    assert "--pipeline-id" in deploy
    assert "databricks bundle run -t prod connect_transcript_sentiment_job" in deploy
    assert "--params contacts=20,batch_label=production" in deploy
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in ci
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in deploy


def test_domain_bootstrap_uses_full_resource_names():
    bootstrap = (ROOT / "scripts" / "bootstrap_identities.sh").read_text()
    assert "get-domain domains/customer-experience" in bootstrap
    assert "get-domain domains/contact-centre" in bootstrap
    assert 'path: "members"' in bootstrap
    assert 'group_name: "contact_centre_analysts"' in bootstrap


def test_genie_examples_use_serialized_space_array_contract():
    notebook = (ROOT / "notebooks" / "03_register_domain_assets.py").read_text()
    assert '"metric_views": [' in notebook
    assert '["sample_questions"]' in notebook
    assert '"question": ["Which queue had the highest negative share?"]' in notebook
    assert 'serialized["benchmarks"] = {' in notebook
    assert '"answer": [' in notebook
    assert "uuid.uuid4" not in notebook
