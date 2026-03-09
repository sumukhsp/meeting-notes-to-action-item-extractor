from __future__ import annotations

from datetime import date
import uuid
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from .agents import BaselineAgent, PriorityAgent, TaskClassifierAgent, TranscriptParserAgent, SummaryAgent
from .logging_utils import RunLogger
from .schemas import (
    BaselineAgentInput,
    LogEventType,
    PriorityAgentInput,
    SystemState,
    TaskClassifierInput,
    TranscriptParserInput,
    SummaryAgentInput,
)
from .state_machine import StateMachine


@dataclass
class RunConfig:
    seed: int
    meeting_date: date = field(default_factory=date.today)
    max_steps: int = 20
    run_dir: str = "runs"


@dataclass
class RunOutput:
    run_id: str
    items: list[Any]
    baseline_items: list[Any]
    state_machine: StateMachine
    metrics: dict[str, Any]
    output_json: dict[str, Any]
    agent_messages: list[dict[str, Any]] = field(default_factory=list)
    active_agent: str = ""
    analysis: dict[str, Any] = field(default_factory=dict)

def to_master_json(items: list[Any]) -> dict[str, Any]:
    tasks = []
    for it in items:
        tasks.append({
            "task_id": it.id,
            "title": it.title,
            "owner": it.owner,
            "deadline": it.deadline,
            "category": it.category,
            "priority": it.priority_label,
            "score": it.priority_score,
            "confidence": it.confidence_score,
        })
    return {"tasks": tasks}

def _round3(x: float) -> float:
    """Round *x* to 3 decimal places (avoids Pyre ``round`` overload issue)."""
    return int(x * 1000.0 + 0.5) / 1000.0


def _new_run_id() -> str:
    hex_str: str = uuid.uuid4().hex
    return hex_str[:12]


def run_pipeline(raw_text: str, cfg: RunConfig, stop_flag: dict[str, bool] | None = None) -> RunOutput:
    t0 = perf_counter()
    run_id = _new_run_id()
    logger = RunLogger(run_id=run_id, run_dir=cfg.run_dir)
    sm = StateMachine(seed=cfg.seed, max_steps=cfg.max_steps)
    agent_messages: list[dict[str, Any]] = []

    def stopped() -> bool:
        return bool(stop_flag and stop_flag.get("stop"))

    from .tools import ToolContext
    logger.log(LogEventType.RUN_START, {"seed": cfg.seed})

    try:
        ctx = ToolContext(seed=cfg.seed, meeting_date=cfg.meeting_date)

        # Explicit workflow milestone: transcript received
        t = sm.transition("receive_transcript", SystemState.TRANSCRIPT_RECEIVED)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())

        if stopped():
            sm.transition("stop", SystemState.STOPPED)
            logger.log(LogEventType.RUN_END, {"status": "stopped"})
            return RunOutput(run_id=run_id, items=[], baseline_items=[], state_machine=sm,
                             metrics={}, output_json=to_master_json([]),
                             agent_messages=agent_messages, active_agent="")

        # ── PARSING ──────────────────────────────────────────────────────────
        t = sm.transition("start_parse", SystemState.PARSING)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
        parser = TranscriptParserAgent()
        r1 = parser.run(TranscriptParserInput(raw_text=raw_text), ctx, logger)
        agent_messages.append({
            "agent": "parser",
            "message": f"Parsed {len(r1.transcript.turns)} turns and extracted {len(r1.items)} candidate action items.",
            "state": SystemState.PARSING.value,
        })

        # Explicit workflow milestone: tasks extracted
        t = sm.transition("tasks_extracted", SystemState.TASKS_EXTRACTED)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())

        if stopped():
            t = sm.transition("stop", SystemState.STOPPED)
            logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
            logger.log(LogEventType.RUN_END, {"status": "stopped"})
            return RunOutput(run_id=run_id, items=[], baseline_items=[], state_machine=sm,
                             metrics={}, output_json=to_master_json([]),
                             agent_messages=agent_messages, active_agent="parser")

        # ── CLASSIFYING ──────────────────────────────────────────────────────
        t = sm.transition("start_classify", SystemState.CLASSIFYING)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
        classifier = TaskClassifierAgent()
        r2 = classifier.run(TaskClassifierInput(items=r1.items), ctx, logger)
        agent_messages.append({
            "agent": "classifier",
            "message": f"Classified {len(r1.items)} items → {len(r2.items)} after deduplication (owner/deadline/category assigned).",
            "state": SystemState.CLASSIFYING.value,
        })

        if stopped():
            t = sm.transition("stop", SystemState.STOPPED)
            logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
            logger.log(LogEventType.RUN_END, {"status": "stopped"})
            return RunOutput(run_id=run_id, items=[], baseline_items=[], state_machine=sm,
                             metrics={}, output_json=to_master_json([]),
                             agent_messages=agent_messages, active_agent="classifier")

        # ── PRIORITIZING ─────────────────────────────────────────────────────
        t = sm.transition("start_prioritize", SystemState.PRIORITIZING)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
        prioritizer = PriorityAgent()
        r3 = prioritizer.run(PriorityAgentInput(items=r2.items), ctx, logger)
        p1 = sum(1 for i in r3.items if i.priority_label == "P1")
        p2 = sum(1 for i in r3.items if i.priority_label == "P2")
        p3 = sum(1 for i in r3.items if i.priority_label == "P3")
        agent_messages.append({
            "agent": "prioritizer",
            "message": f"Prioritized {len(r3.items)} items: P1={p1}, P2={p2}, P3={p3}.",
            "state": SystemState.PRIORITIZING.value,
        })

        # ── SUMMARIZING ──────────────────────────────────────────────────────
        t = sm.transition("start_summarize", SystemState.SUMMARIZING)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
        summarizer = SummaryAgent()
        r4 = summarizer.run(SummaryAgentInput(raw_text=raw_text, items=r3.items), ctx, logger)
        agent_messages.append({
            "agent": "summarizer",
            "message": f"Generated summary and identified {len(r4.analysis.get('decisions_made', []))} decisions.",
            "state": SystemState.SUMMARIZING.value,
        })

        t = sm.transition("summarized", SystemState.COMPLETED)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())

        # ── BASELINE COMPARISON ───────────────────────────────────────────
        baseline_agent = BaselineAgent()
        baseline_result = baseline_agent.run(
            BaselineAgentInput(raw_text=raw_text), ctx, logger,
        )
        baseline_items = baseline_result.items
        agent_messages.append({
            "agent": "baseline",
            "message": f"Baseline extracted {len(baseline_items)} items (single-pass, no dedup).",
            "state": SystemState.COMPLETED.value,
        })

        # Backward-compatibility milestone
        t2 = sm.transition("done", SystemState.DONE)
        logger.log(LogEventType.STATE_TRANSITION, t2.model_dump())

        items = r3.items
        output_json = to_master_json(items)

        n = len(items)
        n_owner = sum(1 for i in items if i.owner and i.owner != "Unassigned")
        n_deadline = sum(1 for i in items if i.deadline)
        n_p1 = sum(1 for i in items if i.priority_label == "P1")
        n_p2 = sum(1 for i in items if i.priority_label == "P2")
        n_p3 = sum(1 for i in items if i.priority_label == "P3")
        mean_conf = _round3(sum(float(i.confidence_score) for i in items) / n) if n else 0.0

        processing_time_ms = int((perf_counter() - t0) * 1000)
        metrics = {
            "items_count": n,
            "items_with_owner": n_owner,
            "owner_rate": _round3(n_owner / n) if n else 0.0,
            "items_with_deadline": n_deadline,
            "deadline_rate": _round3(n_deadline / n) if n else 0.0,
            "p1_count": n_p1,
            "p1_rate": _round3(n_p1 / n) if n else 0.0,
            "p2_count": n_p2,
            "p3_count": n_p3,
            "mean_confidence_score": mean_conf,
            "baseline_items_count": len(baseline_items),
            "same_count_as_baseline": int(n == len(baseline_items)),
            "processing_time_ms": processing_time_ms,
        }
        logger.log(LogEventType.METRICS, metrics)
        logger.log(LogEventType.RUN_END, {"status": "ok"})
        logger.write_summary({"run_id": run_id, "metrics": metrics, "output_json": output_json})

        return RunOutput(
            run_id=run_id,
            items=items,
            baseline_items=baseline_items,
            state_machine=sm,
            metrics=metrics,
            output_json=output_json,
            agent_messages=agent_messages,
            active_agent="summarizer",
            analysis=r4.analysis,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        t = sm.transition("error", SystemState.ERROR)
        logger.log(LogEventType.STATE_TRANSITION, t.model_dump())
        logger.log(LogEventType.ERROR, {"error": str(e)})
        logger.log(LogEventType.RUN_END, {"status": "error"})
        return RunOutput(
            run_id=run_id,
            items=[],
            baseline_items=[],
            state_machine=sm,
            metrics={},
            output_json={},
            agent_messages=[],
            active_agent="",
            analysis={},
        )
