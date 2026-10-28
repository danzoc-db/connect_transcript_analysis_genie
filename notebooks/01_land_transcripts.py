# Databricks notebook source
"""Land an idempotent batch of synthetic Contact Lens transcript JSON.

DATA PRIVACY NOTICE: every transcript is synthetically generated at runtime for a fictional
company (Northwind Energy). No real customer, employee or personal data is used.
"""

import sys
from pathlib import Path


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parents[1]
    except NameError:
        notebook_path = (
            dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        )
        return (Path("/Workspace") / notebook_path.lstrip("/")).parents[1]


sys.path.insert(0, str(_project_root() / "src"))

from connect_sentiment.generator import generate_contacts, random_for_batch, write_contacts

dbutils.widgets.text("volume_path", "")
dbutils.widgets.text("contacts", "400")
dbutils.widgets.text("batch_label", "initial")
dbutils.widgets.text("seed", "42")
dbutils.widgets.text("plant_bad", "true")
dbutils.widgets.text("skip_if_exists", "true")

volume_path = dbutils.widgets.get("volume_path")
batch_label = dbutils.widgets.get("batch_label")
contacts = generate_contacts(
    random_for_batch(int(dbutils.widgets.get("seed")), batch_label),
    int(dbutils.widgets.get("contacts")),
    plant_bad=dbutils.widgets.get("plant_bad").lower() == "true",
    batch_label=batch_label,
)
written = write_contacts(
    volume_path,
    contacts,
    batch_label=batch_label,
    skip_if_exists=dbutils.widgets.get("skip_if_exists").lower() == "true",
)
print(f"Wrote {written} transcript files to {volume_path} for batch {batch_label}")
