from typing import Literal

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    ok: bool
    detail: str | None = None
    version: str | None = None
    latency_ms: float | None = None
    models: list[str] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    llm_model: str
    components: dict[str, ComponentStatus]
