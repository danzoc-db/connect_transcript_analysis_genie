"""Public scoring contract tests (offline)."""

from __future__ import annotations

from connect_sentiment.scoring import (
    RetryableGatewayError,
    build_sentiment_request,
    derive_trajectory,
    parse_sentiment_response,
    score_with_retry,
)


def test_parses_final_json_text_after_reasoning():
    response = {
        "model": "system.ai.gpt-oss-20b-1",
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "reasoning", "summary": [{"text": "Administrative call."}]},
                        {"type": "text", "text": '{"sentiment": "neutral"}'},
                    ]
                }
            }
        ],
    }
    result = parse_sentiment_response(response)
    assert result.sentiment == "neutral"
    assert result.error is None
    assert result.model == "system.ai.gpt-oss-20b-1"


def test_invalid_label_normalises_to_null_with_error():
    response = {
        "choices": [{"message": {"content": '{"sentiment": "happy"}'}}],
    }
    result = parse_sentiment_response(response)
    assert result.sentiment is None
    assert "outside contract" in result.error


def test_request_has_strict_contract_and_label_definitions():
    request = build_sentiment_request(
        "catalog.schema.transcript_sentiment",
        "I only need to submit a meter reading.",
    )
    assert request["model"] == "catalog.schema.transcript_sentiment"
    assert request["temperature"] == 0
    sentiment = request["response_format"]["json_schema"]["schema"]["properties"]["sentiment"]
    assert sentiment["enum"] == ["positive", "negative", "neutral", "mixed"]
    system = request["messages"][0]["content"].lower()
    assert "neutral" in system and "factual" in system
    assert "mixed" in system and "both" in system
    assert "meter reading" in system


def test_trajectory_uses_opening_mid_closing_without_confidence():
    result = derive_trajectory("negative", "mixed", "positive")
    assert result.shift == "recovered"
    assert result.path == "negative>mixed>positive"

    short = derive_trajectory("neutral", None, "negative")
    assert short.shift == "deteriorated"
    assert short.path == "neutral>negative"


def test_gateway_retry_recovers_from_429():
    attempts = []

    def send(_request):
        attempts.append(1)
        if len(attempts) == 1:
            raise RetryableGatewayError(429, "model units unavailable")
        return {"choices": [{"message": {"content": '{"sentiment":"positive"}'}}]}

    result = score_with_retry(
        send,
        build_sentiment_request("catalog.schema.service", "Thank you, that fixed it."),
        max_attempts=2,
        sleep=lambda _seconds: None,
    )
    assert len(attempts) == 2
    assert result.sentiment == "positive"
