"""Ollama client (localhost only) with JSON-schema structured output.

Every call is logged to logs/llm_calls.log as one JSON line: model, durations,
token counts and outcome — used to compare models and spot slow/failed calls.
"""

import json
import logging
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """User-facing LLM failure (connection, timeout, invalid output)."""


@dataclass
class CallStats:
    model: str
    seconds: float
    load_seconds: float
    prompt_tokens: int
    output_tokens: int
    tokens_per_second: float


_call_log: logging.Logger | None = None


def _calls_logger() -> logging.Logger:
    global _call_log
    if _call_log is None:
        _call_log = logging.getLogger("llm.calls")
        _call_log.propagate = False
        d = get_settings().log_dir
        d.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(d / "llm_calls.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(message)s"))
        _call_log.addHandler(h)
        _call_log.setLevel(logging.INFO)
    return _call_log


def _record(entry: dict[str, Any]) -> None:
    _calls_logger().info(json.dumps(entry, ensure_ascii=False))


def chat_json(
    *,
    system: str,
    user: str,
    schema: type[T],
    model: str | None = None,
    purpose: str = "",
    retries: int = 1,
    transport: httpx.BaseTransport | None = None,
) -> tuple[T, CallStats]:
    """Calls Ollama /api/chat constrained to `schema`'s JSON schema and validates the result."""
    s = get_settings()
    model = model or s.llm_model
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": schema.model_json_schema(),
        "keep_alive": s.llm_keep_alive,
        "options": {"temperature": s.llm_temperature, "num_ctx": s.llm_num_ctx},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last_error = "unknown"
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        entry: dict[str, Any] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "purpose": purpose, "attempt": attempt + 1, "prompt_chars": len(system) + len(user)}
        try:
            with httpx.Client(base_url=s.ollama_base_url, timeout=httpx.Timeout(s.llm_timeout_seconds, connect=5), transport=transport) as client:
                r = client.post("/api/chat", json=body)
            if r.status_code == 404:
                raise LLMError(f"Ollama에 '{model}' 모델이 없습니다. 'ollama pull {model}'로 설치하거나 설정에서 다른 모델을 선택하세요.")
            r.raise_for_status()
            data = r.json()
        except LLMError as exc:
            _record(entry | {"ok": False, "error": str(exc)})
            raise
        except httpx.TimeoutException as exc:
            _record(entry | {"ok": False, "error": "timeout", "seconds": round(time.perf_counter() - t0, 1)})
            raise LLMError(f"LLM 응답 시간이 {s.llm_timeout_seconds}초를 초과했습니다.") from exc
        except httpx.HTTPError as exc:
            _record(entry | {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            raise LLMError(f"Ollama에 연결할 수 없습니다 ({s.ollama_base_url}). 'brew services start ollama'로 실행 상태를 확인하세요.") from exc

        elapsed = time.perf_counter() - t0
        eval_ns = data.get("eval_duration") or 1
        stats = CallStats(
            model=model,
            seconds=round(elapsed, 2),
            load_seconds=round((data.get("load_duration") or 0) / 1e9, 2),
            prompt_tokens=data.get("prompt_eval_count") or 0,
            output_tokens=data.get("eval_count") or 0,
            tokens_per_second=round((data.get("eval_count") or 0) / (eval_ns / 1e9), 1),
        )
        content = (data.get("message") or {}).get("content", "")
        try:
            parsed = schema.model_validate_json(content)
        except ValidationError as exc:
            last_error = f"JSON 형식 오류: {exc.errors()[0].get('msg', '')}"
            _record(entry | stats.__dict__ | {"ok": False, "error": last_error, "output_preview": content[:300]})
            log.warning("LLM %s returned invalid JSON (attempt %d): %s", purpose, attempt + 1, last_error)
            continue
        _record(entry | stats.__dict__ | {"ok": True})
        log.info("LLM %s: %s %.1fs (%d→%d tokens, %.1f tok/s)", purpose, model, stats.seconds, stats.prompt_tokens, stats.output_tokens, stats.tokens_per_second)
        return parsed, stats
    raise LLMError(f"LLM이 올바른 형식의 결과를 만들지 못했습니다 ({last_error}).")


def installed_models(transport: httpx.BaseTransport | None = None) -> list[str]:
    s = get_settings()
    try:
        with httpx.Client(base_url=s.ollama_base_url, timeout=5, transport=transport) as client:
            return [m["name"] for m in client.get("/api/tags").raise_for_status().json().get("models", [])]
    except httpx.HTTPError as exc:
        raise LLMError("Ollama에 연결할 수 없습니다.") from exc


def unload(model: str) -> None:
    """Asks Ollama to free the model now (keep_alive=0). Best effort."""
    s = get_settings()
    try:
        with httpx.Client(base_url=s.ollama_base_url, timeout=10) as client:
            client.post("/api/generate", json={"model": model, "keep_alive": 0})
    except httpx.HTTPError:
        pass
