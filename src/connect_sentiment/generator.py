"""Generate coherent synthetic Amazon Connect Contact Lens transcripts."""

from __future__ import annotations

import hashlib
import json
import random
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ARCS = ("positive", "negative", "neutral", "mixed")
ARC_WEIGHTS = (0.30, 0.25, 0.25, 0.20)
QUEUES = (
    "Account Services",
    "Billing",
    "Boiler Care",
    "Complaints",
    "Moving Home",
    "Payments",
    "Sales",
    "Smart Meters",
)
AGENTS = (
    ("a-1001", "Aoife"),
    ("a-1002", "Ciaran"),
    ("a-1003", "Niamh"),
    ("a-1004", "Darragh"),
    ("a-1005", "Siobhan"),
    ("a-1006", "Eoin"),
)
COUNTIES = ("Dublin", "Cork", "Galway", "Limerick", "Kildare", "Meath", "Wexford")
ACCOUNT_ID = "123456789012"
INSTANCE_ID = "6f1c2a8e-4b7d-4e0a-9c2f-3d5e7a1b9c40"


def random_for_batch(base_seed: int, batch_label: str) -> random.Random:
    """Return a reproducible RNG whose contacts are unique to a batch label."""
    material = f"{base_seed}:{batch_label}".encode("ascii")
    derived_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return random.Random(derived_seed)


# Each intent is a complete mini-story. Lines are never selected across intents.
INTENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "estimated_high_bill",
        "queue": "Billing",
        "reason": "High bill query",
        "opening": (
            "My bill is {amount} euro, nearly double normal, and I think the estimate is wrong.",
            "I have another unusually high estimated bill and need it corrected.",
        ),
        "agent": (
            "I can see this bill used an estimated reading. Do you have the meter reading?",
            "I have entered {reading} and recalculated the account.",
            "The corrected bill will be issued today.",
        ),
    },
    {
        "id": "payment_plan",
        "queue": "Payments",
        "reason": "Payment plan and arrears",
        "opening": (
            "I am behind by {amount} euro and worried about the arrears letter.",
            "I need an affordable payment plan because I cannot clear the balance at once.",
        ),
        "agent": (
            "We can review an affordable plan and nobody will be disconnected while we do that.",
            "I can spread the balance over twelve months.",
            "I will also send the support-fund information.",
        ),
    },
    {
        "id": "missed_smart_meter_appointment",
        "queue": "Smart Meters",
        "reason": "Missed smart meter appointment",
        "opening": (
            "The installer never arrived for my smart meter appointment this morning.",
            "This is a missed smart meter appointment and I took time off work.",
        ),
        "agent": (
            "I am sorry nobody turned up. I can see the missed appointment.",
            "I have escalated it and reserved a replacement slot for {day}.",
            "A confirmation text and complaint reference are on the way.",
        ),
    },
    {
        "id": "book_smart_meter_install",
        "queue": "Smart Meters",
        "reason": "Book smart meter installation",
        "opening": (
            "I received an invitation and would like to book the smart meter installation.",
            "Can I arrange a first smart meter installation at my home?",
        ),
        "agent": (
            "I can arrange that. I will check the available installation slots.",
            "There is an appointment on {day}.",
            "I have booked it and sent the preparation instructions.",
        ),
    },
    {
        "id": "moving_home",
        "queue": "Moving Home",
        "reason": "Move home",
        "opening": (
            "I am moving to {county} and need to transfer my energy account.",
            "I need to close my old address and open the account at my new home.",
        ),
        "agent": (
            "I will take the closing and opening meter readings.",
            "Both addresses are updated and the direct debit date is unchanged.",
            "Your final and opening statements will arrive by email.",
        ),
    },
    {
        "id": "boiler_breakdown",
        "queue": "Boiler Care",
        "reason": "Boiler breakdown",
        "opening": (
            "My boiler has stopped and there is no heat or hot water.",
            "I have boiler cover and need an engineer because the heating is not working.",
        ),
        "agent": (
            "First, can you confirm there is no smell of gas?",
            "Thank you. I have completed the safety check and booked an engineer for {day}.",
            "You will receive the engineer tracking link by text.",
        ),
    },
    {
        "id": "formal_complaint",
        "queue": "Complaints",
        "reason": "Complaint escalation",
        "opening": (
            "I want to make a formal complaint after calling several times.",
            "Nobody has responded to my complaint and I need it escalated.",
        ),
        "agent": (
            "I am sorry you had to call again. I will take ownership of the case.",
            "It is escalated to customer resolution with a five-day deadline.",
            "I have sent the reference and next steps.",
        ),
    },
    {
        "id": "tariff_quote",
        "queue": "Sales",
        "reason": "Tariff quote",
        "opening": (
            "I would like to compare the available tariffs before my current plan ends.",
            "Can you explain the fixed and variable tariff options for my account?",
        ),
        "agent": (
            "I will compare the eligible tariffs using your recent annual usage.",
            "The fixed plan provides price certainty, while the variable plan can change.",
            "I have sent both quotes with the unit rates and standing charges.",
        ),
    },
    {
        "id": "direct_debit_date",
        "queue": "Account Services",
        "reason": "Change direct debit date",
        "opening": (
            "I only need to change the date of my direct debit.",
            "Can you move my direct debit to the twenty-eighth?",
        ),
        "agent": (
            "I can update that after the security check.",
            "The payment date is now the twenty-eighth.",
            "The change will apply from the next billing cycle.",
        ),
    },
)

INTENTS_BY_QUEUE = {
    queue: tuple(intent for intent in INTENTS if intent["queue"] == queue) for queue in QUEUES
}

REACTIONS = {
    "positive": (
        "That is exactly what I needed.",
        "This is much easier than I expected.",
        "Thanks, you have resolved it quickly.",
    ),
    "negative": (
        "That does not undo the time I have already lost.",
        "I have heard this before and do not trust it will happen.",
        "I am still unhappy and will put the complaint in writing.",
    ),
    "neutral": (
        "Okay, I understand.",
        "Please confirm the details.",
        "That is all I needed today.",
    ),
    "mixed": (
        "I am still frustrated about what happened.",
        "At least you have explained the next step clearly.",
        "I am not happy with the delay, but thank you for resolving it now.",
    ),
}


def _fill(text: str, context: dict[str, Any]) -> str:
    return text.format(**context)


def _turn(
    rng: random.Random,
    participant: str,
    content: str,
    offset: int,
) -> tuple[dict[str, Any], int]:
    duration = max(1_200, int(len(content.split()) * rng.uniform(300, 420)))
    result = {
        "Id": str(uuid.UUID(int=rng.getrandbits(128))),
        "ParticipantId": participant,
        "Content": content,
        "BeginOffsetMillis": offset,
        "EndOffsetMillis": offset + duration,
    }
    return result, offset + duration + rng.randint(300, 1_800)


def _dialogue(
    rng: random.Random,
    intent: dict[str, Any],
    arc: str,
    agent_name: str,
    context: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    lines = [
        ("AGENT", f"Thanks for calling BGE, you are speaking with {agent_name}. How can I help?"),
        ("CUSTOMER", _fill(rng.choice(intent["opening"]), context)),
    ]
    for agent_line, customer_line in zip(intent["agent"], REACTIONS[arc], strict=True):
        lines.append(("AGENT", _fill(agent_line, context)))
        lines.append(("CUSTOMER", _fill(customer_line, context)))
    lines.extend(
        [
            ("AGENT", "Is there anything else I can help you with today?"),
            ("CUSTOMER", "No, that is everything. Goodbye."),
        ]
    )

    turns: list[dict[str, Any]] = []
    offset = rng.randint(800, 2_500)
    for participant, content in lines:
        item, offset = _turn(rng, participant, content, offset)
        turns.append(item)
    return turns, offset


def _build_contact(
    rng: random.Random,
    start_ts: datetime,
    batch_label: str,
) -> dict[str, Any]:
    queue = rng.choice(QUEUES)
    intent = rng.choice(INTENTS_BY_QUEUE[queue])
    arc = rng.choices(ARCS, weights=ARC_WEIGHTS, k=1)[0]
    agent_id, agent_name = rng.choice(AGENTS)
    context = {
        "amount": rng.choice((186, 248, 312, 402, 520)),
        "reading": rng.randint(10_000, 69_999),
        "county": rng.choice(COUNTIES),
        "day": rng.choice(("tomorrow morning", "Wednesday", "Friday afternoon", "Monday")),
    }
    transcript, total_ms = _dialogue(rng, intent, arc, agent_name, context)
    contact_id = str(uuid.UUID(int=rng.getrandbits(128)))
    return {
        "Version": "1.1.0",
        "AccountId": ACCOUNT_ID,
        "Channel": "VOICE",
        "ContentMetadata": {"Output": "Redacted", "RedactionTypes": ["PII"]},
        "JobStatus": "COMPLETED",
        "LanguageCode": "en-IE",
        "Participants": [
            {"ParticipantId": "AGENT", "ParticipantRole": "AGENT"},
            {"ParticipantId": "CUSTOMER", "ParticipantRole": "CUSTOMER"},
        ],
        "CustomerMetadata": {
            "ContactId": contact_id,
            "InstanceId": INSTANCE_ID,
            "InputS3Uri": f"s3://connect-recordings/{start_ts:%Y/%m/%d}/{contact_id}.wav",
        },
        "ContactAttributes": {
            "Queue": intent["queue"],
            "ContactReason": intent["reason"],
            "AgentId": agent_id,
            "AgentName": agent_name,
            "CustomerCounty": context["county"],
            "CustomerSegment": rng.choice(("Residential", "Residential", "Residential", "SME")),
            "InitiationTimestamp": start_ts.isoformat().replace("+00:00", "Z"),
            "HoldDurationSeconds": rng.randint(20, 1_500),
            "Transferred": arc == "negative" and rng.random() < 0.35,
            "QaArcLabel": arc,
            "QaIntentId": intent["id"],
            "BatchLabel": batch_label,
        },
        "ConversationCharacteristics": {"TotalConversationDurationMillis": total_ms},
        "Transcript": transcript,
    }


def generate_contacts(
    rng: random.Random,
    n: int,
    *,
    plant_bad: bool = True,
    batch_label: str = "initial",
    days_back: int = 60,
    now: datetime | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Build Contact Lens records and their relative paths without writing files."""
    base = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    contacts: list[tuple[Path, dict[str, Any]]] = []
    for _ in range(n):
        day = base - timedelta(days=rng.randint(0, days_back))
        started = day.replace(hour=rng.randint(8, 19), minute=rng.randint(0, 59))
        contact = _build_contact(rng, started, batch_label)
        contact_id = contact["CustomerMetadata"]["ContactId"]
        filename = f"{contact_id}_analysis_{started:%Y-%m-%dT%H:%M:%SZ}.json"
        contacts.append(
            (Path(f"{started:%Y}") / f"{started:%m}" / f"{started:%d}" / filename, contact)
        )

    if plant_bad and n >= 3:
        contacts[0][1]["ContactAttributes"]["PlantedDefect"] = "missing_contact_id"
        contacts[0][1]["CustomerMetadata"]["ContactId"] = None
        contacts[1][1]["ContactAttributes"]["PlantedDefect"] = "failed_job"
        contacts[1][1]["JobStatus"] = "FAILED"
        contacts[2][1]["ContactAttributes"]["PlantedDefect"] = "no_customer_turns"
        contacts[2][1]["Transcript"] = [
            turn for turn in contacts[2][1]["Transcript"] if turn["ParticipantId"] == "AGENT"
        ]
    return contacts


def _batch_already_exists(root: Path, batch_label: str) -> bool:
    for path in root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="ascii"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if payload.get("ContactAttributes", {}).get("BatchLabel") == batch_label:
            return True
    return False


def write_contacts(
    volume_path: str | Path,
    contacts: list[tuple[Path, dict[str, Any]]],
    *,
    batch_label: str = "initial",
    skip_if_exists: bool = False,
) -> int:
    """Write contacts below the standard Contact Lens export path."""
    root = Path(volume_path) / "connect" / "Analysis" / "Voice"
    if skip_if_exists and root.exists() and _batch_already_exists(root, batch_label):
        return 0

    written = 0
    for index, (relative, contact) in enumerate(contacts):
        path = root / relative
        if contact["CustomerMetadata"]["ContactId"] is None:
            path = path.with_name(re.sub(r"^[^_]+", f"invalid-{index}", path.name, count=1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(contact, ensure_ascii=True) + "\n", encoding="ascii")
        written += 1
    return written
