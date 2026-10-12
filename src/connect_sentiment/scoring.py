"""Sentiment contract shared by the scoring job and offline tests."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SENTIMENT_LABELS = ("positive", "negative", "neutral", "mixed")

SYSTEM_PROMPT = """Classify the sentiment expressed by the CUSTOMER text.
Return exactly one JSON object with one field named sentiment.

Labels:
- positive: praise, gratitude, relief, satisfaction, or clear happiness.
- negative: complaint, anger, worry, disappointment, or clear dissatisfaction.
- neutral: factual or administrative language without praise or dissatisfaction.
- mixed: both positive and negative sentiment are materially present.

Examples:
Customer: I only need to submit a meter reading. It is 45231.
{"sentiment":"neutral"}
Customer: Nobody arrived and I lost a day, but you have fixed it now. Thank you.
{"sentiment":"mixed"}
Customer: That solved it quickly. I really appreciate your help.
{"sentiment":"positive"}

Do not infer the agent's sentiment. Do not return a confidence score or explanation."""

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "sentiment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "sentiment": {
                    "type": "string",
                    "enum": list(SENTIMENT_LABELS),
                }
            },
            "required": ["sentiment"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class SentimentResult:
    sentiment: str | None
    error: str | None
    model: str | None = None


@dataclass(frozen=True)
class SentimentTrajectory:
    shift: str
    path: str


class RetryableGatewayError(RuntimeError):
    """A gateway response that should be retried with backoff."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def build_sentiment_request(model_service: str, customer_text: str) -> dict[str, Any]:
    """Build one OpenAI-compatible gateway request."""
    return {
        "model": model_service,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Customer text:\n{customer_text}"},
        ],
        "response_format": RESPONSE_FORMAT,
        "temperature": 0,
        "max_tokens": 800,
    }


def _final_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            item.get("text")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
        ]
        if texts:
            return texts[-1]
    raise ValueError("response has no final text content")


def _json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def parse_sentiment_response(response: dict[str, Any]) -> SentimentResult:
    """Parse only the final text item and enforce the exact SQL-function contract."""
    model = response.get("model")
    try:
        choices = response["choices"]
        content = choices[0]["message"]["content"]
        value = _json_object(_final_text(content)).get("sentiment")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return SentimentResult(None, f"invalid gateway response: {exc}", model)
    if not isinstance(value, str) or value.lower() not in SENTIMENT_LABELS:
        return SentimentResult(None, f"sentiment outside contract: {value!r}", model)
    return SentimentResult(value.lower(), None, model)


def derive_trajectory(
    opening: str | None,
    middle: str | None,
    closing: str | None,
) -> SentimentTrajectory:
    """Derive a stable contact-level path from temporal sentiment windows."""
    if opening in {"negative", "mixed"} and closing == "positive":
        shift = "recovered"
    elif opening in {"positive", "neutral"} and closing == "negative":
        shift = "deteriorated"
    else:
        shift = "stable"
    path = ">".join(value for value in (opening, middle, closing) if value)
    return SentimentTrajectory(shift=shift, path=path)


def score_with_retry(
    send: Callable[[dict[str, Any]], dict[str, Any]],
    request: dict[str, Any],
    *,
    max_attempts: int = 6,
    sleep: Callable[[float], None] = time.sleep,
) -> SentimentResult:
    """Send one request, retrying only rate-limit and unavailable responses."""
    for attempt in range(max_attempts):
        try:
            return parse_sentiment_response(send(request))
        except RetryableGatewayError as exc:
            if exc.status_code not in {429, 503} or attempt == max_attempts - 1:
                return SentimentResult(None, f"gateway HTTP {exc.status_code}: {exc}")
            sleep(min(30.0, 2**attempt))
        except Exception as exc:
            return SentimentResult(None, f"gateway request failed: {exc}")
    return SentimentResult(None, "gateway retry loop exhausted")
