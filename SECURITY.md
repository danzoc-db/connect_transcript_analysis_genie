# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub private vulnerability
reporting for this repository.

Include the affected file or resource, reproduction steps, impact and any suggested mitigation.
Do not include workspace tokens, OAuth secrets, transcript data or personal information.

## Deployment security

- Store Databricks credentials only in GitHub Actions secrets or an approved secret manager.
- Prefer GitHub OIDC workload identity federation over stored client secrets.
- Use separate deployment and runtime service principals.
- Grant the runtime identity only the catalog, schema, volume and model-service permissions it
  needs.
- Keep production changes behind pull requests and required CI checks.
- Do not use this synthetic demo repository to store real contact-centre transcripts.

## Data privacy

All data in this repository is synthetically generated and fictional ("Northwind Energy" is not
a real company). The repository contains no personal data and no workspace credentials, and
its public CI is not connected to any Databricks workspace.
