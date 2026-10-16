from connect_sentiment.pt_endpoint import create_payload, update_payload


def test_create_payload_uses_model_unit_pt_contract():
    payload = create_payload(
        "connect-sentiment-gpt-oss-20b",
        "system.ai.gpt-oss-20b",
        "1",
        0,
    )

    entity = payload["config"]["served_entities"][0]
    assert entity["provisioned_model_units"] == 0
    assert entity["entity_name"] == "system.ai.gpt-oss-20b"
    assert "min_provisioned_throughput" not in entity
    assert "max_provisioned_throughput" not in entity
    assert "scale_to_zero_enabled" not in entity
    assert "ai_gateway" not in payload
    assert {"key": "demo_project", "value": "connect_transcript_genie"} in payload["tags"]
    assert all(tag["key"] != "project" for tag in payload["tags"])


def test_update_payload_preserves_entity_and_only_sets_units():
    existing = {
        "name": "gpt-oss-20b",
        "entity_name": "system.ai.gpt-oss-20b",
        "entity_version": "1",
        "provisioned_model_units": 50,
        "workload_size": "Small",
    }

    payload = update_payload(existing, 0)

    assert payload == {
        "config": {
            "served_entities": [
                {
                    "name": "gpt-oss-20b",
                    "entity_name": "system.ai.gpt-oss-20b",
                    "entity_version": "1",
                    "provisioned_model_units": 0,
                }
            ]
        }
    }
