"""Behaviours of the synthetic Amazon Connect generator (offline)."""

from __future__ import annotations

import json
import random
from pathlib import Path

from connect_sentiment.generator import (
    INTENTS,
    QUEUES,
    generate_contacts,
    random_for_batch,
    write_contacts,
)

REQUIRED_TOP = {
    "Version",
    "Channel",
    "JobStatus",
    "Participants",
    "CustomerMetadata",
    "ContactAttributes",
    "Transcript",
}


def test_contact_is_contact_lens_json_with_no_source_sentiment():
    contacts = generate_contacts(random.Random(0), n=8, plant_bad=False)
    assert len(contacts) == 8
    for _rel, contact in contacts:
        assert REQUIRED_TOP.issubset(contact)
        assert contact["Channel"] == "VOICE"
        assert "Sentiment" not in contact
        assert "sentiment" not in json.dumps(contact).lower().replace("qaarclabel", "")
        assert contact["CustomerMetadata"]["ContactId"]
        assert contact["ContactAttributes"]["QaArcLabel"] in {
            "positive",
            "negative",
            "neutral",
            "mixed",
        }
        assert contact["ContactAttributes"]["QaIntentId"]
        assert contact["ContactAttributes"]["Queue"] in QUEUES
        turns = contact["Transcript"]
        assert turns, "transcript must have turns"
        offsets = [t["BeginOffsetMillis"] for t in turns]
        assert offsets == sorted(offsets)
        assert turns[0]["ParticipantId"] == "AGENT"
        assert any(t["ParticipantId"] == "CUSTOMER" for t in turns)


def test_written_files_are_ascii_and_path_matches_connect_layout(tmp_path: Path):
    contacts = generate_contacts(random.Random(1), n=5, plant_bad=False)
    written = write_contacts(tmp_path, contacts)
    assert written == 5
    root = tmp_path / "connect" / "Analysis" / "Voice"
    files = list(root.rglob("*.json"))
    assert len(files) == 5
    for path in files:
        raw = path.read_text(encoding="ascii")
        assert all(ord(c) < 128 for c in raw)
        parts = path.relative_to(root).parts
        assert len(parts) == 4
        year, month, day, name = parts
        assert len(year) == 4 and len(month) == 2 and len(day) == 2
        assert "_analysis_" in name and name.endswith(".json")
        payload = json.loads(raw)
        assert payload["CustomerMetadata"]["ContactId"] in name


def test_bge_appears_only_in_agent_greetings():
    contacts = generate_contacts(random.Random(2), n=20, plant_bad=False)
    for _rel, contact in contacts:
        for turn in contact["Transcript"]:
            text = turn["Content"]
            if "BGE" in text:
                assert turn["ParticipantId"] == "AGENT"
                assert text.startswith("Thanks for calling BGE") or "calling BGE" in text


def test_turns_within_a_contact_stay_on_one_intent():
    contacts = generate_contacts(random.Random(3), n=30, plant_bad=False)
    for _rel, contact in contacts:
        intent_id = contact["ContactAttributes"]["QaIntentId"]
        joined = " ".join(t["Content"] for t in contact["Transcript"]).lower()
        # A missed-appointment story must not also be a first-time booking.
        if intent_id == "missed_smart_meter_appointment":
            assert "book the smart meter" not in joined
            assert "nobody turned up" in joined or "missed" in joined
        if intent_id == "book_smart_meter_install":
            assert "nobody turned up" not in joined
            assert "second missed" not in joined


def test_every_queue_has_an_intent_and_large_batches_are_balanced():
    assert {intent["queue"] for intent in INTENTS} == set(QUEUES)
    contacts = generate_contacts(
        random_for_batch(42, "queue-balance"),
        n=800,
        plant_bad=False,
        batch_label="queue-balance",
    )
    counts = {
        queue: sum(
            contact["ContactAttributes"]["Queue"] == queue for _, contact in contacts
        )
        for queue in QUEUES
    }
    assert all(70 <= count <= 130 for count in counts.values()), counts


def test_plants_bad_records_for_quality_rules():
    contacts = generate_contacts(random.Random(4), n=20, plant_bad=True)
    defects = [c["ContactAttributes"].get("PlantedDefect") for _, c in contacts]
    assert "missing_contact_id" in defects
    assert "failed_job" in defects
    assert "no_customer_turns" in defects
    missing = next(
        c
        for _, c in contacts
        if c["ContactAttributes"].get("PlantedDefect") == "missing_contact_id"
    )
    assert missing["CustomerMetadata"]["ContactId"] is None
    failed = next(
        c for _, c in contacts if c["ContactAttributes"].get("PlantedDefect") == "failed_job"
    )
    assert failed["JobStatus"] == "FAILED"
    empty = next(
        c for _, c in contacts if c["ContactAttributes"].get("PlantedDefect") == "no_customer_turns"
    )
    assert all(t["ParticipantId"] != "CUSTOMER" for t in empty["Transcript"])


def test_second_drop_adds_files_without_skipping(tmp_path: Path):
    first = generate_contacts(random.Random(5), n=4, plant_bad=False, batch_label="drop1")
    write_contacts(tmp_path, first, batch_label="drop1")
    second = generate_contacts(random.Random(6), n=3, plant_bad=False, batch_label="drop2")
    added = write_contacts(tmp_path, second, batch_label="drop2")
    assert added == 3
    files = list((tmp_path / "connect" / "Analysis" / "Voice").rglob("*.json"))
    assert len(files) == 7
    skipped = write_contacts(tmp_path, first, batch_label="drop1", skip_if_exists=True)
    assert skipped == 0


def test_batch_label_produces_reproducible_but_distinct_contact_ids():
    first = generate_contacts(
        random_for_batch(42, "initial"),
        n=5,
        plant_bad=False,
        batch_label="initial",
    )
    repeated = generate_contacts(
        random_for_batch(42, "initial"),
        n=5,
        plant_bad=False,
        batch_label="initial",
    )
    second = generate_contacts(
        random_for_batch(42, "second-drop"),
        n=5,
        plant_bad=False,
        batch_label="second-drop",
    )

    first_ids = [contact["CustomerMetadata"]["ContactId"] for _, contact in first]
    repeated_ids = [contact["CustomerMetadata"]["ContactId"] for _, contact in repeated]
    second_ids = [contact["CustomerMetadata"]["ContactId"] for _, contact in second]
    assert first_ids == repeated_ids
    assert set(first_ids).isdisjoint(second_ids)
