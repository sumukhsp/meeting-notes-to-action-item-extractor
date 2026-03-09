# Meeting Notes → Action Items Extractor

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

## Run the App

```bash
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

## CLI Evaluation

```bash
python -m src
```

## Environment Variables

Copy `.env.example` to `.env` and fill in values if using an LLM API key:

```bash
copy .env.example .env
```

## Project Structure

```
├── app.py                    # Streamlit UI (7 tabs)
├── src/
│   ├── agents.py             # Parser, Classifier, Prioritizer, Baseline agents
│   ├── guardrails.py         # Tool allowlist, output validation, timeout
│   ├── orchestrator.py       # Pipeline runner + RunOutput
│   ├── state_machine.py      # Explicit state machine with transition logging
│   ├── tools.py              # All tool functions (deterministic, seedable)
│   ├── schemas.py            # Pydantic models for all data types
│   ├── evaluation.py         # 10-scenario evaluation harness, 5 metrics
│   ├── scenarios.py          # 10 built-in test scenarios
│   ├── logging_utils.py      # JSONL logger + run replay
│   └── baseline_single_agent.py  # Reference single-agent implementation
├── docs/
│   ├── architecture.md       # System design + agent roles + tool schemas
│   ├── agent_interaction_diagram.md  # Mermaid sequence diagram
│   └── evaluation_report.md  # Metrics results for all 10 scenarios
├── runs/                     # JSONL logs + summary JSON (auto-created)
└── requirements.txt
```

## Multi-Agent Architecture

```
IDLE → PARSING (ParserAgent) → CLASSIFYING (ClassifierAgent)
     → PRIORITIZING (PrioritizerAgent) → DONE
     Any state → ERROR | STOPPED
```

Three specialized agents + one single-agent baseline for comparison:
- **Parser**: Splits transcript, extracts candidate action sentences, scores confidence
- **Classifier**: Assigns owner/deadline/category, deduplicates
- **Prioritizer**: Scores 1-10 on urgency/deadline/keyword signals, assigns P1/P2/P3

## UI Panels

| Tab | Contents |
|-----|----------|
| 📋 Tasks | Priority-badged task table with owner, deadline, category, confidence |
| 🤖 Agents | Agent cards with active-agent highlighting |
| 🔄 State | ASCII state diagram + full transition history |
| 💬 Messages | Timestamped tool calls, agent messages, state transitions |
| 📊 Metrics | 5 metrics + priority distribution vs. baseline bar charts |
| 📄 Logs | JSONL event viewer + past run replay |
| 📥 JSON | Structured output + download |

## Reproducibility

Every run uses a **seed** for deterministic output:

```python
from src.orchestrator import run_pipeline, RunConfig
from datetime import date

cfg = RunConfig(seed=42, meeting_date=date(2026, 2, 27))
out1 = run_pipeline("Alice: @Bob send the deck by Friday", cfg)
out2 = run_pipeline("Alice: @Bob send the deck by Friday", cfg)
assert [i.title for i in out1.items] == [i.title for i in out2.items]  # ✅ SAME
```

## Demo Script (5-7 min)

1. Show `docs/architecture.md` — architecture + state machine
2. Launch `streamlit run app.py`, set **Seed = 7**
3. Select **scenario_09_priority_words** → click **▶ Start**
4. Walk through each tab (Tasks → Agents → State → Messages → Metrics)
5. Click **Run 10 Scenarios** → show per-scenario table in Metrics tab
6. Reset, re-run same seed → compare JSON output (identical)
7. Select **scenario_10_failureish** (sparse/noisy) → show graceful handling
