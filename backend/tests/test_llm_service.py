import json

import httpx
import pytest

from app.agents.llm_schemas import FinalMinutes
from app.config import get_settings
from app.services import llm_service

GOOD = {"meeting_summary": "요약", "discussion_items": [], "decisions": [], "action_items": [], "open_issues": [], "next_meeting_checks": []}


def ollama(responses):
    """MockTransport returning the given (status, content) pairs in order; records requests."""
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        status, content = responses[len(seen) - 1]
        body = {"message": {"content": content}, "eval_count": 40, "eval_duration": 2_000_000_000, "prompt_eval_count": 300, "load_duration": 10**9}
        return httpx.Response(status, json=body if status == 200 else {"error": "x"})

    return httpx.MockTransport(handler), seen


def call(transport):
    return llm_service.chat_json(system="sys", user="usr", schema=FinalMinutes, model="qwen3:14b", purpose="test", transport=transport)


def test_success_sends_schema_and_records_stats():
    t, seen = ollama([(200, json.dumps(GOOD, ensure_ascii=False))])
    result, stats = call(t)
    assert result.meeting_summary == "요약"
    req = seen[0]
    assert req["think"] is False and req["stream"] is False
    assert req["format"]["properties"]["action_items"]["type"] == "array"
    assert req["options"]["num_ctx"] == get_settings().llm_num_ctx
    assert (stats.prompt_tokens, stats.output_tokens, stats.tokens_per_second, stats.load_seconds) == (300, 40, 20.0, 1.0)
    log = (get_settings().log_dir / "llm_calls.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert json.loads(log)["ok"] is True and json.loads(log)["purpose"] == "test"


def test_invalid_json_is_retried_once():
    t, seen = ollama([(200, '{"meeting_summary": 1'), (200, json.dumps(GOOD))])
    result, _ = call(t)
    assert result.meeting_summary == "요약" and len(seen) == 2


def test_invalid_json_twice_raises():
    t, _ = ollama([(200, "not json"), (200, "{}")])
    with pytest.raises(llm_service.LLMError, match="올바른 형식"):
        call(t)


def test_missing_model_message():
    t, _ = ollama([(404, "")])
    with pytest.raises(llm_service.LLMError, match="ollama pull qwen3:14b"):
        call(t)


def test_connection_error_message():
    def boom(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(llm_service.LLMError, match="연결할 수 없습니다"):
        call(httpx.MockTransport(boom))


def test_timeout_message():
    def slow(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(llm_service.LLMError, match="초과"):
        call(httpx.MockTransport(slow))
