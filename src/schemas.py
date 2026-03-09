from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    PARSER = "parser"
    CLASSIFIER = "classifier"
    PRIORITIZER = "prioritizer"
    BASELINE = "baseline"


class SystemState(str, Enum):
    IDLE = "IDLE"
    TRANSCRIPT_RECEIVED = "TRANSCRIPT_RECEIVED"
    PARSING = "PARSING"
    TASKS_EXTRACTED = "TASKS_EXTRACTED"
    CLASSIFYING = "CLASSIFYING"
    PRIORITIZING = "PRIORITIZING"
    COMPLETED = "COMPLETED"
    DONE = "DONE"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class ToolName(str, Enum):
    TRANSCRIPT_PARSE = "transcript_parse"
    EXTRACT_ACTION_ITEMS = "extract_action_items"
    TASK_CLASSIFY = "task_classify"
    PRIORITY_SCORE = "priority_score"
    DEDUPLICATE = "deduplicate"


class TranscriptTurn(BaseModel):
    speaker: str
    text: str


class Transcript(BaseModel):
    raw_text: str
    turns: list[TranscriptTurn]


class ActionItem(BaseModel):
    id: str
    title: str
    owner: str = "Unassigned"
    deadline: str | None = None
    deadline_parse_method: str | None = None
    category: Literal[
        "Engineering",
        "Product",
        "Marketing",
        "Sales",
        "Operations",
        "Customer Success",
        "Leadership",
        "Other",
    ] = "Other"
    priority_score: int = 1
    priority_label: Literal["P1", "P2", "P3"] = "P3"
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["Pending", "In Progress", "Done"] = "Pending"
    source_speakers: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    priority_rule_hits: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: ToolName
    input: dict[str, Any]


class ToolResult(BaseModel):
    tool: ToolName
    output: dict[str, Any]


class StateTransition(BaseModel):
    timestamp: datetime
    previous_state: SystemState
    event: str
    next_state: SystemState


class LogEventType(str, Enum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    STATE_TRANSITION = "state_transition"
    AGENT_INVOKE = "agent_invoke"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MESSAGE = "message"
    METRICS = "metrics"
    ERROR = "error"
    GUARDRAIL = "guardrail"


class LogEvent(BaseModel):
    run_id: str
    ts: datetime
    type: LogEventType
    payload: dict[str, Any]


# Agent I/O models (strict, typed)
class TranscriptParserInput(BaseModel):
    raw_text: str


class TranscriptParserOutput(BaseModel):
    transcript: Transcript
    items: list[ActionItem]


class TaskClassifierInput(BaseModel):
    items: list[ActionItem]


class TaskClassifierOutput(BaseModel):
    items: list[ActionItem]


class PriorityAgentInput(BaseModel):
    items: list[ActionItem]


class PriorityAgentOutput(BaseModel):
    items: list[ActionItem]


class BaselineAgentInput(BaseModel):
    raw_text: str


class BaselineAgentOutput(BaseModel):
    items: list[ActionItem]


# Evaluation models
class EvalScenarioResult(BaseModel):
    scenario_key: str
    items_count: int
    baseline_count: int
    owner_rate: float
    deadline_rate: float
    p1_rate: float
    mean_confidence: float
    jaccard_vs_baseline: float
