# Architecture Document
## Meeting Notes → Action Items Extractor

### Overview

A **multi-agent pipeline** that converts raw meeting transcripts into a structured, prioritized task list. The system uses three specialized agents orchestrated through an explicit state machine, with full observability (JSONL logging), schema-validated inter-agent messages, guardrails, and a baseline single-agent comparison.

---

### System Components

```
┌──────────────────────────────────────────────────────┐
│                    Orchestrator                      │
│  StateMachine: IDLE→PARSING→CLASSIFYING→PRIORITIZING │
│                         →DONE / ERROR / STOPPED      │
│                                                      │
│  ┌──────────┐   ┌─────────────┐   ┌─────────────┐   │
│  │  Parser  │──▶│ Classifier  │──▶│ Prioritizer │   │
│  │  Agent   │   │   Agent     │   │   Agent     │   │
│  └──────────┘   └─────────────┘   └─────────────┘   │
│       │               │                  │           │
│  [transcript_parse]  [task_classify]  [priority_score]│
│  [extract_action_items] [deduplicate]               │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Baseline Agent (single-pass, no dedup)      │   │
│  └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
         │
         ▼ JSONL log (run_id.jsonl) + summary JSON
         ▼ Streamlit UI (7 tabs)
```

---

### Agent Roles

| Agent | Role | Tools Used | Output |
|-------|------|-----------|--------|
| **Parser** | Reads raw transcript, identifies speakers and candidate action sentences | `transcript_parse`, `extract_action_items` | `list[ActionItem]` with confidence scores |
| **Classifier** | Assigns owner, deadline, category; removes duplicates | `task_classify`, `deduplicate` | Enriched, deduplicated `list[ActionItem]` |
| **Prioritizer** | Scores each item 1–10 on urgency/impact signals; assigns P1/P2/P3 | `priority_score` | Sorted `list[ActionItem]` |
| **Baseline** | Single-pass reference (no separation, no dedup) | all 4 tools combined | `list[ActionItem]` for metric comparison |

---

### State Machine

| From State | Event | To State |
|-----------|-------|---------|
| IDLE | start | PARSING |
| PARSING | parsed | CLASSIFYING |
| CLASSIFYING | classified | PRIORITIZING |
| PRIORITIZING | prioritized | DONE |
| Any | stop | STOPPED |
| Any | error | ERROR |

---

### Tool Schemas

#### `transcript_parse(raw_text, ctx) → Transcript`
- Splits lines by `Speaker: text` pattern
- Groups multi-line speaker turns

#### `extract_action_items(transcript, ctx) → list[ActionItem]`
- Detects action sentences via keyword + pattern matching
- Assigns `confidence_score`: 0.9 (explicit keyword), 0.65 (pattern match), 0.4 (implicit)

#### `task_classify(items, ctx) → list[ActionItem]`
- Owner: `@mention` > "I'll/We'll" → speaker > "Name will" pattern > "Unassigned"
- Deadline: `within N hours` > `tomorrow` > `by <date>` > `today/EOD` > fuzzy parse
- Category: 7 regex rule sets (Engineering, Product, Marketing, Sales, Operations, Customer Success, Leadership, Other)

#### `deduplicate(items) → list[ActionItem]`
- Key: `(owner.lower(), deadline.lower(), normalized_title.lower())`
- Removes exact duplicates after normalization

#### `priority_score(items, ctx) → list[ActionItem]`
- Base score: 1
- +3 for launch/release/Q2 keywords
- +2 if deadline within 14 days
- +2 for critical/urgent/asap keywords
- +2 for risk/freeze/scope creep keywords
- +1 for blocked/approval keywords
- +1 for legal/enterprise keywords
- +1 if confidence_score ≥ 0.85
- Clamped to [1,10]; P1≥8, P2≥5, P3<5

---

### Guardrails

| Guardrail | Mechanism |
|-----------|----------|
| Tool allowlist | `validate_tool_call()` — raises if tool not in `ALLOWED_TOOLS` |
| Output schema validation | `validate_output()` — Pydantic validation on all tool outputs |
| Step budget | `StateMachine.max_steps` (default 20) — raises `RuntimeError` if exceeded |
| Tool timeout | `TimeoutGuard(10s)` context manager on every tool call |
| Human override | Stop button sets `stop_flag["stop"] = True`; checked between each agent |

---

### Observability

Every run is assigned a UUID run ID. Events logged to `runs/<run_id>.jsonl`:

| Event Type | When logged |
|-----------|-----------|
| `run_start` | Pipeline begins |
| `state_transition` | Each state change |
| `agent_invoke` | Each agent called |
| `tool_call` | Before each tool (with input) |
| `tool_result` | After each tool (with output) |
| `message` | Agent completion message |
| `metrics` | Final metrics dict |
| `run_end` | Pipeline ends (ok/error/stopped) |

---

### Reproducibility

- Every run accepts a `seed` parameter
- `StateMachine.rng` seeded from `seed`
- `ToolContext.seed` passed to all tools
- Same seed + same transcript → same extracted tasks (deterministic regex engine)
