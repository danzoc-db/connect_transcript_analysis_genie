"""Static checks for portable bundle configuration."""

import re
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
    assert "contact_centre_analytics" in targets


def test_bundle_is_not_wired_to_any_live_workspace():
    text = (ROOT / "databricks.yml").read_text()
    assert "profile:" not in text
    assert "host:" not in text
    assert not re.search(r"warehouse_id: *[0-9a-f]{16}", text)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)


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


def test_public_ci_is_offline_and_deploy_is_a_template():
    workflows = ROOT / ".github" / "workflows"
    assert sorted(p.name for p in workflows.glob("*.yml")) == ["ci.yml"]
    ci = (workflows / "ci.yml").read_text()
    assert "ruff check ." in ci
    assert "pytest -q" in ci
    for wired in (
        "secrets.",
        "DATABRICKS_HOST",
        "DATABRICKS_CLIENT",
        "bundle deploy",
        "bundle run",
    ):
        assert wired not in ci
    template = (ROOT / "templates" / "github-actions" / "deploy.yml.template").read_text()
    assert "scripts/manage_pt_endpoint.py" in template
    assert "--units 0" in template
    assert "databricks bundle deploy -t prod" in template
    assert "scripts/grant_bundle_file_access.py" in template
    assert "databricks bundle run -t prod connect_transcript_sentiment_job" in template
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in template


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
