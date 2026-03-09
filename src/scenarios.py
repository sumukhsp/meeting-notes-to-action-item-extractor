from __future__ import annotations

SCENARIOS: dict[str, str] = {
    "scenario_01_basic": """Alice: Action item: @Bob please send the updated deck by Friday.
Bob: Sure, I will send it by Friday EOD.
Carol: Let's schedule a sync next week to review progress.
""",
    "scenario_02_bug": """Dev: The login is broken in production.
Lead: Action item: @Nina fix the login issue ASAP.
Nina: I will fix it by tomorrow.
""",
    "scenario_03_research": """PM: We need to explore vendors for transcription.
PM: Action item: Raj will research options by next week.
""",
    "scenario_04_admin": """Ops: Action item: @Sam update access for the new intern by today.
""",
    "scenario_05_deliverable": """Manager: Please submit the weekly report by Monday.
""",
    "scenario_06_multiple": """Alice: Action item: @Bob follow up with the client by Wednesday.
Bob: Action item: I will investigate the error logs by tomorrow.
Carol: Let's meet on Thursday to close open items.
""",
    "scenario_07_noisy": """Alice: So, um, we talked about many things.
Bob: Yeah.
Alice: Action item: @Bob please draft the proposal by 10 March.
""",
    "scenario_08_owner_in_text": """Sarah: John will schedule the demo by Friday.
""",
    "scenario_09_priority_words": """Lead: Action item: @Max urgent - fix payment bug today.
""",
    "scenario_10_failureish": """Speaker: Action item: please do the thing by some day maybe.
""",
}
