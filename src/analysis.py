"""Heuristic-based meeting analysis generator.

Produces a structured report (summary, discussion points, decisions,
questions, risks) from the raw transcript and extracted action items.
No LLM calls – everything is regex / keyword driven.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────────

_SPEAKER_RE = re.compile(r"^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?):", re.MULTILINE)

_DECISION_RE = [
    re.compile(p, re.I)
    for p in [
        r"\b(?:decided|agreed|approved|confirmed|finalized?)\b",
        r"\b(?:target|goal|deadline)\s+(?:is|will be|set to)\b",
        r"\b(?:will\s+(?:go|be)\s+with)\b",
        r"\b(?:let'?s\s+(?:go|do|proceed|set|freeze))\b",
        r"\b(?:freez(?:e|ing)|frozen)\b",
        r"\b(?:must|shall)\s+be\b",
    ]
]

_RISK_RE = re.compile(
    r"\b(?:risk|blocker|blocked|delay|scope\s*creep|depend(?:ency|ent)|"
    r"critical|urgent|ASAP|concern|issue|problem|bottleneck|constraint|"
    r"challenge|tight\s+deadline|overdue|slip(?:page)?)\b",
    re.I,
)

_QUESTION_RE = re.compile(
    r"\b(?:need to confirm|should we|waiting for|pending|TBD|"
    r"to be (?:decided|confirmed)|follow[\s-]?up|any update)\b",
    re.I,
)


def _extract_speakers(raw_text: str) -> list[str]:
    return list(dict.fromkeys(_SPEAKER_RE.findall(raw_text)))


def _clean_line(line: str) -> str:
    return re.sub(r"^[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?:\s*", "", line.strip())


def _get_attr(obj: Any, name: str, default: Any = "") -> Any:
    return getattr(obj, name, default) or default


# ── public API ───────────────────────────────────────────────────────────────

def generate_analysis(
    raw_text: str,
    items: list[Any],
    meeting_date: date | None = None,
) -> dict[str, Any]:
    """Return a structured analysis dict with six sections."""
    speakers = _extract_speakers(raw_text)
    categories = list(dict.fromkeys(_get_attr(i, "category", "Other") for i in items))

    return {
        "meeting_summary": _build_summary(speakers, items, categories, meeting_date),
        "key_discussion_points": _discussion_points(items, categories),
        "decisions_made": _decisions(raw_text, items),
        "action_items": [
            {
                "task": _get_attr(i, "title"),
                "owner": _get_attr(i, "owner", "Unassigned"),
                "deadline": _get_attr(i, "deadline", "–"),
                "priority": _get_attr(i, "priority_label", "P3"),
            }
            for i in items
        ],
        "open_questions": _questions(raw_text),
        "risks_blockers": _risks(raw_text, items),
    }


def _build_summary(
    speakers: list[str],
    items: list[Any],
    categories: list[str],
    meeting_date: date | None,
) -> str:
    parts: list[str] = []
    if meeting_date:
        parts.append(f"Meeting held on {meeting_date.isoformat()}")
    if speakers:
        names = ", ".join(speakers) if len(speakers) <= 5 else f"{len(speakers)} participants"
        parts.append(f"with {names}" if meeting_date else f"Meeting with {names}")
    if items:
        parts.append(f"The discussion produced {len(items)} action item(s)")
        if categories and categories != ["Other"]:
            parts.append(f"spanning {', '.join(c for c in categories if c != 'Other')}")
    p1 = [i for i in items if _get_attr(i, "priority_label") == "P1"]
    if p1:
        parts.append(f"{len(p1)} item(s) flagged as critical (P1) priority")
    owners: dict[str, int] = {}
    for i in items:
        o = _get_attr(i, "owner", "Unassigned")
        if o != "Unassigned":
            owners[o] = owners.get(o, 0) + 1
    if owners:
        busiest = max(owners, key=lambda k: owners[k])
        parts.append(f"{busiest} leads with the most assignments ({owners[busiest]})")
    return ". ".join(parts) + "." if parts else "No data available."


def _discussion_points(items: list[Any], categories: list[str]) -> list[str]:
    pts: list[str] = []
    for cat in categories:
        n = sum(1 for i in items if _get_attr(i, "category") == cat)
        pts.append(f"{cat}: {n} action item(s) identified")
    owners = sorted({_get_attr(i, "owner") for i in items if _get_attr(i, "owner") != "Unassigned"})
    if owners:
        pts.append(f"Ownership distributed across {len(owners)} team member(s): {', '.join(owners)}")
    dl = sum(1 for i in items if _get_attr(i, "deadline"))
    if dl:
        pts.append(f"{dl} of {len(items)} item(s) have explicit deadlines")
    return pts


def _decisions(raw_text: str, items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in raw_text.splitlines():
        clean = _clean_line(line)
        if not clean or len(clean) < 10:
            continue
        if any(p.search(clean) for p in _DECISION_RE):
            key = clean.lower()[:50]
            if key not in seen:
                seen.add(key)
                out.append(clean)
    # Also synthesise decisions from items with both owner + deadline
    for i in items:
        o = _get_attr(i, "owner", "Unassigned")
        dl = _get_attr(i, "deadline")
        if o != "Unassigned" and dl:
            text = f"{_get_attr(i, 'title')} assigned to {o} with deadline {dl}"
            key = text.lower()[:50]
            if key not in seen:
                seen.add(key)
                out.append(text)
    return out


def _questions(raw_text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        clean = _clean_line(line)
        if not clean:
            continue
        if "?" in clean or _QUESTION_RE.search(clean):
            key = clean.lower()[:50]
            if key not in seen:
                seen.add(key)
                out.append(clean)
    return out


def _risks(raw_text: str, items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in raw_text.splitlines():
        clean = _clean_line(line)
        if len(clean) > 15 and _RISK_RE.search(clean):
            key = clean.lower()[:50]
            if key not in seen:
                seen.add(key)
                out.append(clean)
    # P1 items
    for i in items:
        if _get_attr(i, "priority_label") == "P1":
            t = f"Critical priority: {_get_attr(i, 'title')} (P1)"
            key = t.lower()[:50]
            if key not in seen:
                seen.add(key)
                out.append(t)
    # Missing assignments
    unassigned = sum(1 for i in items if _get_attr(i, "owner", "Unassigned") == "Unassigned")
    if unassigned:
        out.append(f"{unassigned} task(s) without assigned owner")
    no_dl = sum(1 for i in items if not _get_attr(i, "deadline"))
    if no_dl:
        out.append(f"{no_dl} task(s) without explicit deadline")
    return out


# ── Markdown export ──────────────────────────────────────────────────────────

def analysis_to_markdown(analysis: dict[str, Any]) -> str:
    """Convert analysis dict to downloadable Markdown."""
    lines = ["# 📊 Analysis Results\n"]

    lines.append("## Meeting Summary\n")
    lines.append(analysis.get("meeting_summary", "") + "\n")

    _section(lines, "Key Discussion Points", analysis.get("key_discussion_points"))
    _section(lines, "Decisions Made", analysis.get("decisions_made"))

    ai = analysis.get("action_items", [])
    if ai:
        lines.append("\n## Action Items\n")
        lines.append("| Task | Owner | Deadline | Priority |")
        lines.append("|------|-------|----------|----------|")
        for row in ai:
            lines.append(
                f"| {row['task']} | {row['owner']} | {row.get('deadline', '–')} | {row.get('priority', 'P3')} |"
            )

    _section(lines, "Open Questions / Follow-ups", analysis.get("open_questions"))
    _section(lines, "Risks / Blockers", analysis.get("risks_blockers"))

    return "\n".join(lines) + "\n"


def _section(lines: list[str], title: str, items: list[str] | None) -> None:
    if items:
        lines.append(f"\n## {title}\n")
        for item in items:
            lines.append(f"- {item}")
