#!/usr/bin/env python3
"""Grant runtime access that must be applied after a production bundle deploy."""

from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="Databricks CLI profile; omit for environment auth")
    parser.add_argument("--bundle", default="connect_transcript_analysis_genie")
    parser.add_argument("--target", default="prod")
    parser.add_argument("--runtime-principal", required=True)
    parser.add_argument("--pipeline-id", required=True)
    args = parser.parse_args()

    client = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    current_user = client.current_user.me().user_name
    files_path = f"/Workspace/Users/{current_user}/.bundle/{args.bundle}/{args.target}/files"
    status = client.api_client.do(
        "GET",
        "/api/2.0/workspace/get-status",
        query={"path": files_path},
    )
    object_id = status["object_id"]
    client.api_client.do(
        "PATCH",
        f"/api/2.0/permissions/directories/{object_id}",
        body={
            "access_control_list": [
                {
                    "service_principal_name": args.runtime_principal,
                    "permission_level": "CAN_READ",
                }
            ]
        },
    )
    print(f"Granted {args.runtime_principal} CAN_READ on {files_path}")
    client.api_client.do(
        "PATCH",
        f"/api/2.0/permissions/pipelines/{args.pipeline_id}",
        body={
            "access_control_list": [
                {
                    "service_principal_name": args.runtime_principal,
                    "permission_level": "CAN_RUN",
                },
                {
                    "group_name": "contact_centre_engineers",
                    "permission_level": "CAN_RUN",
                },
                {
                    "group_name": "contact_centre_analysts",
                    "permission_level": "CAN_VIEW",
                },
            ]
        },
    )
    print(f"Granted runtime and group access on pipeline {args.pipeline_id}")


if __name__ == "__main__":
    main()
