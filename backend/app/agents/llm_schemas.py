"""JSON schemas the LLM must produce (passed to Ollama as `format`)."""

from pydantic import BaseModel, Field


class LLMDiscussion(BaseModel):
    topic: str
    content: str
    speaker: str = "미확인"
    timestamp: str = "미확인"


class LLMDecision(BaseModel):
    content: str
    evidence: str
    timestamp: str


class LLMAction(BaseModel):
    task: str
    assignee: str
    deadline: str
    evidence: str
    timestamp: str


class ChunkAnalysis(BaseModel):
    discussion_items: list[LLMDiscussion] = Field(default_factory=list, max_length=40)
    decisions: list[LLMDecision] = Field(default_factory=list, max_length=40)
    action_items: list[LLMAction] = Field(default_factory=list, max_length=60)
    open_issues: list[str] = Field(default_factory=list, max_length=40)
    next_meeting_checks: list[str] = Field(default_factory=list, max_length=40)


class FinalMinutes(ChunkAnalysis):
    meeting_summary: str
