# Changelog

All notable changes to this project are documented here.

## Unreleased

- Made the synthetic nature of all data explicit: transcripts use the fictional Northwind Energy
  with invented agents and regions, and data privacy notices now appear in the generator, every
  generated record, the tables, metric view, Genie space and docs.
- Workspace-specific settings are supplied at deploy time so the bundle is portable.
- Public CI runs lint and tests; a GitHub OIDC deployment workflow template is provided for forks.
- Consolidated development notes and generalised the architecture decisions.
- Added coherent synthetic Amazon Connect Contact Lens transcripts with incremental drops and
  planted data-quality defects.
- Added Lakeflow bronze and silver streaming tables with drop and warning expectations.
- Added incremental sentiment trajectory scoring through a Unity AI Gateway model service.
- Added a Unity Catalog metric view, Genie space and domain registration.
- Added Databricks Asset Bundle deployment, tests and GitHub Actions workflows.
