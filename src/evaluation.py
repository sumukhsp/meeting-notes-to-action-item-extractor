from __future__ import annotations

import re
from dataclasses import dataclass, field

from .orchestrator import RunConfig, RunOutput, run_pipeline
from .schemas import EvalScenarioResult
from .scenarios import SCENARIOS


def _round3(x: float) -> float:
    """Round *x* to 3 decimal places (avoids Pyre ``round`` overload issue)."""
    return int(x * 1000.0 + 0.5) / 1000.0


def _norm_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 @]+", "", s)
    return s


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class EvalResult:
    scenarios: int
    scenario_results: list[EvalScenarioResult] = field(default_factory=list)
    # Aggregate metrics
    mean_title_jaccard_vs_baseline: float = 0.0
    mean_owner_rate: float = 0.0
    mean_deadline_rate: float = 0.0
    mean_p1_rate: float = 0.0
    mean_confidence: float = 0.0


def run_evaluation(seed: int = 7) -> EvalResult:
    scenario_results: list[EvalScenarioResult] = []
    j_scores: list[float] = []
    owner_rates: list[float] = []
    deadline_rates: list[float] = []
    p1_rates: list[float] = []
    conf_scores: list[float] = []

    for key, raw in SCENARIOS.items():
        out: RunOutput = run_pipeline(raw, RunConfig(seed=seed))
        n = len(out.items)
        nb = len(out.baseline_items)

        titles = {_norm_title(i.title) for i in out.items}
        base_titles = {_norm_title(i.title) for i in out.baseline_items}
        jac = _jaccard(titles, base_titles)

        own_rate = sum(1 for i in out.items if i.owner and i.owner != "Unassigned") / n if n else 0.0
        dl_rate = sum(1 for i in out.items if i.deadline) / n if n else 0.0
        p1_rate = sum(1 for i in out.items if i.priority_label == "P1") / n if n else 0.0
        mean_conf = sum(i.confidence_score for i in out.items) / n if n else 0.0

        j_scores.append(jac)
        owner_rates.append(own_rate)
        deadline_rates.append(dl_rate)
        p1_rates.append(p1_rate)
        conf_scores.append(mean_conf)

        scenario_results.append(
            EvalScenarioResult(
                scenario_key=key,
                items_count=n,
                baseline_count=nb,
                owner_rate=_round3(own_rate),
                deadline_rate=_round3(dl_rate),
                p1_rate=_round3(p1_rate),
                mean_confidence=_round3(mean_conf),
                jaccard_vs_baseline=_round3(jac),
            )
        )

    def avg(lst: list[float]) -> float:
        return _round3(sum(lst) / len(lst)) if lst else 0.0

    return EvalResult(
        scenarios=len(SCENARIOS),
        scenario_results=scenario_results,
        mean_title_jaccard_vs_baseline=avg(j_scores),
        mean_owner_rate=avg(owner_rates),
        mean_deadline_rate=avg(deadline_rates),
        mean_p1_rate=avg(p1_rates),
        mean_confidence=avg(conf_scores),
    )
