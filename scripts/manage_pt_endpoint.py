#!/usr/bin/env python3
"""Create or resize the gpt-oss model-unit PT endpoint through the PT API."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from connect_sentiment.pt_endpoint import (  # noqa: E402
    ENDPOINT_TAGS,
    create_payload,
    update_payload,
)

DEFAULT_ENDPOINT = "connect-sentiment-gpt-oss-20b"
DEFAULT_MODEL = "system.ai.gpt-oss-20b"
DEFAULT_VERSION = "1"


def request(
    client: WorkspaceClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.api_client.do(method, path, body=body)
    return response if isinstance(response, dict) else {}


def get_endpoint(client: WorkspaceClient, name: str) -> dict[str, Any] | None:
    try:
        return request(client, "GET", f"/api/2.0/serving-endpoints/{name}")
    except NotFound:
        return None


def current_entity(endpoint: dict[str, Any]) -> dict[str, Any]:
    entities = endpoint.get("config", {}).get("served_entities", [])
    if len(entities) != 1:
        raise RuntimeError("Expected exactly one served entity on the PT endpoint")
    return entities[0]


def wait_ready(
    client: WorkspaceClient,
    name: str,
    units: int,
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        endpoint = get_endpoint(client, name)
        if endpoint is None:
            raise RuntimeError(f"Endpoint disappeared while waiting: {name}")
        entity = current_entity(endpoint)
        state = endpoint.get("state", {})
        ready = state.get("ready") == "READY"
        update_state = state.get("config_update") in {"NOT_UPDATING", None}
        if entity.get("provisioned_model_units") == units and ready and update_state:
            print(f"Endpoint {name} is ready at {units} provisioned model units")
            return
        time.sleep(10)
    raise TimeoutError(f"Endpoint {name} did not become ready within {timeout_seconds}s")


def ensure_tags(client: WorkspaceClient, endpoint: dict[str, Any]) -> None:
    current_tags = {tag["key"]: tag.get("value", "") for tag in endpoint.get("tags", [])}
    add_tags = [
        tag for tag in ENDPOINT_TAGS if current_tags.get(tag["key"]) != tag["value"]
    ]
    delete_tags = ["project"] if "project" in current_tags else []
    if not add_tags and not delete_tags:
        return
    request(
        client,
        "PATCH",
        f"/api/2.0/serving-endpoints/{endpoint['name']}/tags",
        {"add_tags": add_tags, "delete_tags": delete_tags},
    )
    print(f"Updated governed endpoint tags on {endpoint['name']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="Databricks CLI profile; omit for environment auth")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-version", default=DEFAULT_VERSION)
    parser.add_argument("--units", type=int, choices=(0, 50), default=0)
    parser.add_argument(
        "--runtime-principal",
        help="Service principal application ID that may resize the endpoint",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    client = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    endpoint = get_endpoint(client, args.endpoint)
    if endpoint is None:
        payload = create_payload(
            args.endpoint,
            args.model,
            args.model_version,
            args.units,
        )
        request(client, "POST", "/api/2.0/serving-endpoints/pt", payload)
        print(f"Created PT endpoint {args.endpoint} at {args.units} model units")
    else:
        entity = current_entity(endpoint)
        if (
            entity.get("entity_name") != args.model
            or str(entity.get("entity_version")) != args.model_version
        ):
            raise RuntimeError(
                f"Endpoint {args.endpoint} serves "
                f"{entity.get('entity_name')} v{entity.get('entity_version')}, "
                f"expected {args.model} v{args.model_version}"
            )
        if entity.get("provisioned_model_units") != args.units:
            payload = update_payload(entity, args.units)
            request(
                client,
                "PUT",
                f"/api/2.0/serving-endpoints/pt/{args.endpoint}/config",
                payload,
            )
            print(f"Requested {args.units} model units for {args.endpoint}")
        else:
            print(f"Endpoint {args.endpoint} already has {args.units} model units")

    wait_ready(client, args.endpoint, args.units, args.timeout_seconds)
    endpoint = get_endpoint(client, args.endpoint)
    if endpoint is None:
        raise RuntimeError(f"Endpoint disappeared before tag update: {args.endpoint}")
    ensure_tags(client, endpoint)
    if args.runtime_principal:
        request(
            client,
            "PATCH",
            f"/api/2.0/permissions/serving-endpoints/{endpoint['id']}",
            {
                "access_control_list": [
                    {
                        "service_principal_name": args.runtime_principal,
                        "permission_level": "CAN_MANAGE",
                    }
                ]
            },
        )
        print(f"Granted endpoint lifecycle management to {args.runtime_principal}")


if __name__ == "__main__":
    main()
