import sys
import traceback
from src.orchestrator import run_pipeline, RunConfig

raw = """Alice: Action item: @Bob please send the updated deck by Friday.
Bob: Sure, I will send it by Friday EOD.
"""

print("Running pipeline manually to catch swallowed exceptions...")
try:
    result = run_pipeline(raw, RunConfig(seed=7))
    print("Pipeline returned:", result.items)
    print("Analysis:", result.analysis)
except Exception as e:
    print(f"PIPELINE CRASHED AND REACHED OUTER SCOPE: {e}")
    traceback.print_exc()
