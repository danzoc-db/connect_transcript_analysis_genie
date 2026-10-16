"""Model-unit provisioned-throughput endpoint payloads.

The current DAB provider sends updates to the classic endpoint API. Model-unit
foundation models require the `/serving-endpoints/pt` API, so bootstrap and
capacity changes use this small, explicit adapter.
"""

from __future__ import annotations

from typing import Any

ENDPOINT_TAGS = [
    {"key": "demo_project", "value": "connect_transcript_genie"},
    {"key": "purpose", "value": "transcript_sentiment"},
]


def served_entity(model_name: str, model_version: str, units: int) -> dict[str, Any]:
    """Return the model-unit entity accepted by the PT API."""
    short_name = model_name.rsplit(".", 1)[-1]
    return {
        "name": short_name,
        "entity_name": model_name,
        "entity_version": model_version,
        "provisioned_model_units": units,
    }


def create_payload(
    endpoint_name: str,
    model_name: str,
    model_version: str,
    units: int,
) -> dict[str, Any]:
    """Return a complete create body with no classic endpoint gateway block."""
    return {
        "name": endpoint_name,
        "config": {
            "served_entities": [
                served_entity(model_name, model_version, units),
            ]
        },
        "tags": ENDPOINT_TAGS,
    }


def update_payload(current_entity: dict[str, Any], units: int) -> dict[str, Any]:
    """Preserve the endpoint entity identity and change only model-unit capacity."""
    return {
        "config": {
            "served_entities": [
                {
                    "name": current_entity["name"],
                    "entity_name": current_entity["entity_name"],
                    "entity_version": current_entity["entity_version"],
                    "provisioned_model_units": units,
                }
            ]
        }
    }
