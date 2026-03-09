import sys
from datetime import date
from src.orchestrator import run_pipeline, RunConfig
from src.db import save_run, get_runs_for_user

raw = """Alice: Action item: @Bob please send the updated deck by Friday.
Bob: Sure, I will send it by Friday EOD.
Carol: Let's schedule a sync next week to review progress.
"""

print("Starting pipeline...")
try:
    result = run_pipeline(raw, RunConfig(seed=7))
    print("Pipeline finished.")
    print("Run ID:", result.run_id)
    print("Active Agent:", result.active_agent)
    print("Items:", len(result.items))
    if not result.items:
        print("Pipeline returned no items! Check recent logs.")
    # Now simulate the saving logic
    tasks_dicts = [t.model_dump() for t in result.items]
    
    print("Saving to DB...")
    save_run("admin", result.run_id, str(date.today()), raw, tasks_dicts, result.analysis)
    print("Saved to DB!")
except Exception as e:
    print(f"EXCEPTION CAUGHT: {e}")
    import traceback
    traceback.print_exc()

# Also try fetching runs
runs = get_runs_for_user("admin")
print("Runs length:", len(runs))
