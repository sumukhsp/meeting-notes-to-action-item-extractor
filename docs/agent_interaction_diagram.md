# Agent Interaction Diagram
## Meeting Notes → Action Items Extractor

### Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User / UI
    participant O as Orchestrator
    participant SM as StateMachine
    participant PA as ParserAgent
    participant CA as ClassifierAgent
    participant PRA as PrioritizerAgent
    participant BA as BaselineAgent
    participant L as Logger

    U->>O: run_pipeline(raw_text, cfg)
    O->>SM: transition("start", PARSING)
    SM-->>L: log STATE_TRANSITION [IDLE→PARSING]

    O->>PA: run(raw_text, ctx)
    PA->>L: log AGENT_INVOKE [parser]
    PA->>PA: transcript_parse(raw_text)
    PA->>L: log TOOL_CALL [transcript_parse]
    PA-->>L: log TOOL_RESULT [turns=N]
    PA->>PA: extract_action_items(transcript)
    PA->>L: log TOOL_CALL [extract_action_items]
    PA-->>L: log TOOL_RESULT [items_count=K]
    PA-->>O: AgentResult{items: list[ActionItem]}

    O->>SM: transition("parsed", CLASSIFYING)
    SM-->>L: log STATE_TRANSITION [PARSING→CLASSIFYING]

    O->>CA: run(items, ctx)
    CA->>L: log AGENT_INVOKE [classifier]
    CA->>CA: task_classify(items)
    CA->>L: log TOOL_CALL [task_classify]
    CA-->>L: log TOOL_RESULT [sample items]
    CA->>CA: deduplicate(classified)
    CA->>L: log TOOL_CALL [deduplicate]
    CA-->>L: log TOOL_RESULT [count_after=J]
    CA-->>O: AgentResult{items: list[ActionItem]}

    O->>SM: transition("classified", PRIORITIZING)
    SM-->>L: log STATE_TRANSITION [CLASSIFYING→PRIORITIZING]

    O->>PRA: run(items, ctx)
    PRA->>L: log AGENT_INVOKE [prioritizer]
    PRA->>PRA: priority_score(items)
    PRA->>L: log TOOL_CALL [priority_score]
    PRA-->>L: log TOOL_RESULT [scores]
    PRA-->>O: AgentResult{items: sorted list[ActionItem]}

    Note over O,BA: Baseline comparison (same seed)
    O->>BA: run(raw_text, ctx)
    BA-->>O: AgentResult{items: baseline items}

    O->>SM: transition("prioritized", DONE)
    SM-->>L: log STATE_TRANSITION [PRIORITIZING→DONE]
    O->>L: log METRICS
    O->>L: log RUN_END [status=ok]
    O-->>U: RunOutput{items, baseline_items, metrics, state_machine}
```

---

### Message Protocol (JSON)

All inter-agent communication uses structured `AgentResult` objects:

```json
{
  "message": "Parsed 5 turns and extracted 3 candidate action items.",
  "data": {
    "items": [
      {
        "id": "T001",
        "title": "@Bob please send the updated deck by Friday",
        "owner": "Bob",
        "deadline": "2026-02-28",
        "category": "Sales",
        "priority_score": 4,
        "priority_label": "P3",
        "confidence_score": 0.9,
        "source_speakers": ["Alice"],
        "status": "Pending"
      }
    ]
  }
}
```

### Log Event Protocol (JSONL)

Each line in `runs/<run_id>.jsonl`:

```json
{
  "run_id": "a3f9bc12e4d7",
  "ts": "2026-02-27T17:45:23.412Z",
  "type": "tool_call",
  "payload": {
    "tool": "task_classify",
    "input": {"count": 3}
  }
}
```

### Guardrail Flow

```
Agent.run()
  │
  ├─▶ validate_tool_call(tool_name)
  │     └─ Raises ValueError if not in ALLOWED_TOOLS
  │
  ├─▶ with TimeoutGuard(10s, tool_name):
  │         tool_function(...)
  │     └─ Raises ToolTimeoutError if exceeded
  │
  └─▶ validate_output(items)
        └─ Raises ValueError if schema invalid
```
