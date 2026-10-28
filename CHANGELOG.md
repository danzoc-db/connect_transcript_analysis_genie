# Changelog

All notable changes to this project are documented here.

## Unreleased

- Rebranded synthetic transcripts to the fictional Northwind Energy with fictional agents and
  regions, and added synthetic-data and privacy notices to the generator, records, tables,
  metric view, Genie space and docs.
- Removed workspace-specific values (CLI profile, warehouse and service principal IDs) from the
  bundle; they are now supplied at deploy time.
- Public CI is offline only. The deploy workflow moved to `templates/github-actions/` for use in
  a private fork with GitHub OIDC.
- Removed internal build notes and run evidence.

- Added coherent synthetic Amazon Connect Contact Lens transcripts with incremental drops and
  planted data-quality defects.
- Added Lakeflow bronze and silver streaming tables with drop and warning expectations.
- Added incremental sentiment trajectory scoring through a Unity AI Gateway model service.
- Added a Unity Catalog metric view, Genie space and domain registration.
- Added Databricks Asset Bundle deployment, tests and GitHub Actions workflows.
