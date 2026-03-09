from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .schemas import LogEvent, LogEventType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def new_run_id() -> str:
    hex_str: str = uuid.uuid4().hex
    return hex_str[:12]


@dataclass
class RunLogger:
    run_id: str
    run_dir: str

    @property
    def jsonl_path(self) -> str:
        return os.path.join(self.run_dir, f"{self.run_id}.jsonl")

    def log(self, type_: LogEventType, payload: dict[str, Any]) -> None:
        ensure_dir(self.run_dir)
        evt = LogEvent(run_id=self.run_id, ts=utc_now(), type=type_, payload=payload)
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(evt.model_dump_json())
            f.write("\n")

    def write_summary(self, summary: dict[str, Any]) -> None:
        ensure_dir(self.run_dir)
        path = os.path.join(self.run_dir, f"{self.run_id}.summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    # Convenience helpers (structured, consistent payloads)
    def log_agent_invoke(self, agent: str, input_payload: dict[str, Any]) -> None:
        self.log(LogEventType.AGENT_INVOKE, {"agent": agent, "input": input_payload})

    def log_agent_result(self, agent: str, output_payload: dict[str, Any]) -> None:
        self.log(LogEventType.MESSAGE, {"kind": "agent_result", "agent": agent, "output": output_payload})

    def log_tool_call(self, tool: str, input_payload: dict[str, Any]) -> None:
        self.log(LogEventType.TOOL_CALL, {"tool": tool, "input": input_payload})

    def log_tool_result(self, tool: str, output_payload: dict[str, Any]) -> None:
        self.log(LogEventType.TOOL_RESULT, {"tool": tool, "output": output_payload})

    def log_state_transition(self, previous: str, event: str, next_state: str) -> None:
        self.log(
            LogEventType.STATE_TRANSITION,
            {"timestamp": utc_now().isoformat(), "previous_state": previous, "event": event, "next_state": next_state},
        )

    def log_metrics(self, metrics: dict[str, Any]) -> None:
        self.log(LogEventType.METRICS, metrics)

    def log_error(self, error: str, details: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"error": error}
        if details:
            payload["details"] = details
        self.log(LogEventType.ERROR, payload)


def replay_run(run_dir: str, run_id: str) -> list[LogEvent]:
    """Replay a run from its JSONL file. Returns a list of LogEvent objects in order."""
    jsonl_path = os.path.join(run_dir, f"{run_id}.jsonl")
    events: list[LogEvent] = []
    if not os.path.exists(jsonl_path):
        raise FileNotFoundError(f"Run log not found: {jsonl_path}")
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            evt = LogEvent.model_validate_json(line)
            events.append(evt)
    return events
