"""
CLI entry point: python -m src

Runs the evaluation harness and prints a summary to stdout.
Also validates reproducibility by running the same pipeline twice with the same seed.
"""
from __future__ import annotations

import json
from datetime import date

from .evaluation import run_evaluation
from .orchestrator import RunConfig, run_pipeline


def main() -> None:
    print("=" * 60)
    print("Meeting Notes → Action Items Extractor")
    print("CLI Evaluation Harness")
    print("=" * 60)

    # ── Reproducibility check ────────────────────────────────────────────────
    print("\n[1] Reproducibility check (seed=42)…")
    SEED = 42
    transcript = "Alice: Action item: @Bob please send the updated deck by Friday.\nBob: Sure, I will send it by Friday EOD."
    cfg = RunConfig(seed=SEED)
    r1 = run_pipeline(transcript, cfg)
    r2 = run_pipeline(transcript, cfg)
    titles1 = [i.title for i in r1.items]
    titles2 = [i.title for i in r2.items]
    assert titles1 == titles2, f"REPRODUCIBILITY FAILED:\n  Run1: {titles1}\n  Run2: {titles2}"
    print(f"   ✅  SAME output for both runs (seed={SEED})")
    print(f"   Tasks extracted: {len(r1.items)}")
    for it in r1.items:
        print(f"   [{it.priority_label}] {it.title} → owner={it.owner} deadline={it.deadline} conf={it.confidence_score:.2f}")

    # ── 10-scenario evaluation ───────────────────────────────────────────────
    print("\n[2] Running 10-scenario evaluation (seed=7)…")
    ev = run_evaluation(seed=7)

    print(f"\n   Scenarios evaluated : {ev.scenarios}")
    print(f"   Mean owner rate     : {ev.mean_owner_rate:.1%}")
    print(f"   Mean deadline rate  : {ev.mean_deadline_rate:.1%}")
    print(f"   Mean P1 rate        : {ev.mean_p1_rate:.1%}")
    print(f"   Mean confidence     : {ev.mean_confidence:.3f}")
    print(f"   Jaccard vs baseline : {ev.mean_title_jaccard_vs_baseline:.3f}")

    print("\n   Per-scenario breakdown:")
    header = f"   {'Scenario':<35} {'Items':>5} {'Base':>5} {'Own%':>6} {'DL%':>6} {'P1%':>5} {'Conf':>5} {'Jac':>5}"
    print(header)
    print("   " + "-" * (len(header) - 3))
    for r in ev.scenario_results:
        print(
            f"   {r.scenario_key:<35} {r.items_count:>5} {r.baseline_count:>5}"
            f" {r.owner_rate:>5.0%} {r.deadline_rate:>5.0%}"
            f" {r.p1_rate:>4.0%} {r.mean_confidence:>5.2f} {r.jaccard_vs_baseline:>5.2f}"
        )

    print("\n✅ All checks passed.\n")


if __name__ == "__main__":
    main()
