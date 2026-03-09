from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import ValidationError

from .logging_utils import RunLogger
from .schemas import (
    BaselineAgentInput,
    BaselineAgentOutput,
    PriorityAgentInput,
    PriorityAgentOutput,
    TaskClassifierInput,
    TaskClassifierOutput,
    TranscriptParserInput,
    TranscriptParserOutput,
    ToolName,
)
from .tools import (
    ToolContext,
    deduplicate,
    extract_action_items,
    priority_score,
    task_classify,
    transcript_parse,
)


def _validate_with_retry(model_cls, payload) -> object:
    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return model_cls.model_validate(payload)


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class TranscriptParserAgent:
    def run(self, input_model: TranscriptParserInput, ctx: ToolContext, logger: RunLogger) -> TranscriptParserOutput:
        raw_text = input_model.raw_text
        logger.log_agent_invoke(
            "TranscriptParserAgent",
            {
                "raw_text_len": len(raw_text),
                "raw_text_sha256": _sha256_text(raw_text),
                "raw_text_preview": raw_text[:2000],
            },
        )

        logger.log_tool_call(
            ToolName.TRANSCRIPT_PARSE.value,
            {
                "raw_text_len": len(raw_text),
                "raw_text_sha256": _sha256_text(raw_text),
                "raw_text_preview": raw_text[:2000],
            },
        )
        transcript = transcript_parse(raw_text, ctx)
        logger.log_tool_result(ToolName.TRANSCRIPT_PARSE.value, {"turns": len(transcript.turns)})

        logger.log_tool_call(ToolName.EXTRACT_ACTION_ITEMS.value, {"turns": len(transcript.turns)})
        items = extract_action_items(transcript, ctx)
        logger.log_tool_result(
            ToolName.EXTRACT_ACTION_ITEMS.value,
            {
                "items_count": len(items),
                "sample": [
                    {"id": i.id, "title": i.title[:80], "confidence_score": float(i.confidence_score)} for i in items[:5]
                ],
            },
        )

        output = TranscriptParserOutput(transcript=transcript, items=items)
        validated: TranscriptParserOutput = _validate_with_retry(TranscriptParserOutput, output.model_dump())  # type: ignore[assignment]
        logger.log_agent_result("TranscriptParserAgent", {"items_count": len(validated.items)})
        return validated


@dataclass
class TaskClassifierAgent:
    def run(self, input_model: TaskClassifierInput, ctx: ToolContext, logger: RunLogger) -> TaskClassifierOutput:
        logger.log_agent_invoke("TaskClassifierAgent", {"items_count": len(input_model.items)})

        logger.log_tool_call(ToolName.TASK_CLASSIFY.value, {"count": len(input_model.items)})
        classified = task_classify(input_model.items, ctx)
        logger.log_tool_result(
            ToolName.TASK_CLASSIFY.value,
            {
                "count": len(classified),
                "sample": [
                    {
                        "id": i.id,
                        "owner": i.owner,
                        "deadline": i.deadline,
                        "deadline_parse_method": getattr(i, "deadline_parse_method", None),
                        "category": i.category,
                    }
                    for i in classified[:5]
                ],
            },
        )

        logger.log_tool_call(ToolName.DEDUPLICATE.value, {"count": len(classified)})
        deduped = deduplicate(classified)
        logger.log_tool_result(ToolName.DEDUPLICATE.value, {"count_after": len(deduped)})

        output = TaskClassifierOutput(items=deduped)
        validated: TaskClassifierOutput = _validate_with_retry(TaskClassifierOutput, output.model_dump())  # type: ignore[assignment]
        logger.log_agent_result("TaskClassifierAgent", {"items_count": len(validated.items)})
        return validated


@dataclass
class PriorityAgent:
    def run(self, input_model: PriorityAgentInput, ctx: ToolContext, logger: RunLogger) -> PriorityAgentOutput:
        logger.log_agent_invoke("PriorityAgent", {"items_count": len(input_model.items)})

        logger.log_tool_call(ToolName.PRIORITY_SCORE.value, {"count": len(input_model.items)})
        prioritized = priority_score(input_model.items, ctx)
        logger.log_tool_result(
            ToolName.PRIORITY_SCORE.value,
            {
                "items": [
                    {
                        "id": i.id,
                        "score": int(i.priority_score),
                        "label": i.priority_label,
                        "priority_rule_hits": getattr(i, "priority_rule_hits", None),
                    }
                    for i in prioritized[:10]
                ]
            },
        )

        output = PriorityAgentOutput(items=prioritized)
        validated: PriorityAgentOutput = _validate_with_retry(PriorityAgentOutput, output.model_dump())  # type: ignore[assignment]
        logger.log_agent_result("PriorityAgent", {"items_count": len(validated.items)})
        return validated


@dataclass
class BaselineAgent:
    def run(self, input_model: BaselineAgentInput, ctx: ToolContext, logger: RunLogger) -> BaselineAgentOutput:
        raw_text = input_model.raw_text
        logger.log_agent_invoke(
            "BaselineAgent",
            {
                "raw_text_len": len(raw_text),
                "raw_text_sha256": _sha256_text(raw_text),
                "raw_text_preview": raw_text[:2000],
            },
        )

        transcript = transcript_parse(raw_text, ctx)
        items = extract_action_items(transcript, ctx)
        items = task_classify(items, ctx)
        items = priority_score(items, ctx)

        output = BaselineAgentOutput(items=items)
        validated: BaselineAgentOutput = _validate_with_retry(BaselineAgentOutput, output.model_dump())  # type: ignore[assignment]
        logger.log_agent_result("BaselineAgent", {"items_count": len(validated.items)})
        return validated
