from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from dateutil import parser as date_parser

from .schemas import ActionItem, Transcript, TranscriptTurn, ToolName
from .guardrails import TimeoutGuard, validate_tool_call
from .analysis import generate_analysis

TOOL_TIMEOUT_SECONDS = 10.0


@dataclass
class ToolContext:
    seed: int
    meeting_date: date = field(default_factory=date.today)


# ─────────────────────────────────────────────────────────────────────────────
# Transcript parsing
# ─────────────────────────────────────────────────────────────────────────────

def _split_turns(raw: str) -> list[TranscriptTurn]:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    turns: list[TranscriptTurn] = []
    current_speaker = "Unknown"
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            turns.append(TranscriptTurn(speaker=current_speaker, text="\n".join(buf).strip()))
            buf = []

    for ln in lines:
        m = re.match(r"^([A-Za-z][A-Za-z0-9_ .-]{0,40}):\s*(.*)$", ln)
        if m:
            flush()
            current_speaker = m.group(1).strip()
            rest = m.group(2).strip()
            if rest:
                buf.append(rest)
        else:
            buf.append(ln)
    flush()
    return turns


_ACTION_VERB_RE = re.compile(
    r"\b(draft|prepare|send|review|update|schedule|finalize|fix|implement|file|publish|create|run|"
    r"share|submit|open|pull|compile|shorten|book|coordinate|refresh|set\s+up|set|add|write|"
    r"deliver|organize|approve|lock|integrate|test|validate|rerun|patch|investigate|analyze|research|"
    r"follow\s+up|ping|sync|meet|call|email|shortlist|present|begin|start|launch|finalized|approved|reviewed|"
    r"post|roll\s+out|go\s+live)\b",
    flags=re.IGNORECASE,
)


def _has_action_verb(text: str) -> bool:
    return bool(_ACTION_VERB_RE.search(text))


def _looks_like_non_task(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True

    # Opinions / commentary without a concrete ask
    if re.search(r"\b(i think|i feel|seems like|maybe|probably|kind of)\b", t):
        if not re.search(r"\b(action item|please|can you|could you|i\s+will|i\s*['’]\s*ll|we\s*['’]\s*ll)\b", t):
            return True

    # Constraint / finance commentary phrasing that is often not a task
    if re.search(r"\bbudget\b|\bcost\b|\bpricing\b|\bcapex\b", t) and re.search(r"\bif\b", t):
        if not re.search(r"\b(action item|please|can you|could you|i\s+will|i\s*['’]\s*ll)\b", t):
            return True

    return False


def _infer_owner_from_sentence(sentence: str, speaker: str) -> str:
    s = sentence.strip()

    # @Name mention indicates delegation
    m = re.search(r"\B@([A-Za-z][A-Za-z0-9_\-]{1,30})\b", s)
    if m:
        return m.group(1)

    # Assignment / request pattern: "Taylor, draft ..." / "Taylor, please ..."
    m2 = re.match(r"^(?:action item\s*:\s*)?([A-Z][a-z]+)\s*,\s*(.+)$", s, flags=re.IGNORECASE)
    if m2:
        name = m2.group(1)
        rest = m2.group(2)
        if name.lower() in {
            "sure", "okay", "ok", "yeah", "yep", "no", "yes", "right", "great",
            "thanks", "sorry", "cool", "alright",
        }:
            return speaker

        # If the remainder is a first-person commitment, treat this as an acknowledgement (not delegation).
        if re.match(r"^(i\s+will|i['’]?ll|i\s+can|we\s+will|we['’]?ll|we\s+can)\b", rest.strip(), flags=re.IGNORECASE):
            return speaker

        # Avoid false positives like "Sure, ..." by requiring an action/request cue in the remainder.
        if re.search(r"\b(please|can you|could you)\b", rest, flags=re.IGNORECASE) or _has_action_verb(rest):
            return name

    # "Name please verb" (without comma) — e.g. "Bob please send the deck"
    m3 = re.match(r"^(?:action item\s*:\s*)?([A-Z][a-z]+)\s+(?:please|kindly)\s+(.+)$", s, flags=re.IGNORECASE)
    if m3:
        name = m3.group(1)
        if name.lower() not in {
            "sure", "okay", "ok", "yeah", "yep", "no", "yes", "right", "great",
            "thanks", "sorry", "cool", "alright",
        } and _has_action_verb(m3.group(2)):
            return name

    # "Let's" / collective suggestion → attributed to speaker
    if re.match(r"^let['\u2019]?s\b", s, flags=re.IGNORECASE):
        return speaker

    # Unclear group tasks
    if re.match(r"^(we\s+need\s+to|we\s+should|someone\s+needs\s+to)\b", s, flags=re.IGNORECASE):
        return "Team"

    # Imperative request without explicit assignee ("Send me ...", "Make sure ...")
    # Owner is unknown; treat as team/unassigned responsibility.
    if _has_action_verb(s) and not re.match(r"^(i\s+will|i['’]?ll|i\s+can|we\s+will|we['’']?ll|we\s+can)\b", s, flags=re.IGNORECASE):
        return "Unassigned"

    return speaker


def transcript_parse(raw_text: str, ctx: ToolContext) -> Transcript:
    validate_tool_call(ToolName.TRANSCRIPT_PARSE.value)
    with TimeoutGuard(TOOL_TIMEOUT_SECONDS, ToolName.TRANSCRIPT_PARSE.value):
        turns = _split_turns(raw_text)
        return Transcript(raw_text=raw_text, turns=turns)

    raise RuntimeError("unreachable")


# ─────────────────────────────────────────────────────────────────────────────
# Category classification — 8 categories with richer patterns
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_RULES: list[tuple[str, str]] = [
    # Engineering / Dev
    (r"\bapi\b|\bbackend\b|\bfrontend\b|\bengineering\b|\bqa\b|\bbuild\b|\bdeploy\b"
     r"|\bstable build\b|\bnotification\b|\bpush notification\b|\bios\b|\bandroid\b"
     r"|\bsandbox\b|\bapple\b|\banalytics\b|\btracking\b|\bevent tracking\b"
     r"|\bimplementation\b|\bdevelopment\b", "Engineering"),
    # Product
    (r"\bfeature\b|\bscope\b|\bproduct\b|\bwidgets\b|\bmockups\b|\bdesign\b"
     r"|\bonboarding\b|\bui assets\b|\bapp screens\b|\bapp store\b|\bfeature list\b"
     r"|\bfeature documentation\b|\brequirements\b", "Product"),
    # Marketing
    (r"\blaunch\b|\bemail\b|\blanding page\b|\bdemo video\b|\bcopy\b|\bcampaign\b"
     r"|\bmarketing calendar\b|\bpromo video\b|\bsocial\b|\bteaser\b|\bapp listing\b"
     r"|\bpromotional\b|\bsocial media\b", "Marketing"),
    # Sales
    (r"\bpricing\b|\bsales\b|\benterprise\b|\benablement\b|\bdeck\b|\bclients\b"
     r"|\binvestors\b|\btraction\b", "Sales"),
    # Operations
    (r"\bonboarding\b|\boperations\b|\bdocs\b|\bdocumentation\b|\btraining\b"
     r"|\bsupport training\b|\bfaq\b|\bfaqs\b|\bchecklist\b|\bcoordination\b"
     r"|\blaunch day\b|\bexecution\b", "Operations"),
    # Customer Success
    (r"\bsupport\b|\bcustomer\b|\bfaq\b|\bfaqs\b|\btraining material\b", "Customer Success"),
    # Leadership
    (r"\bapprove\b|\breview\b|\bfreeze\b|\brisk\b|\bcritical\b|\bno delays\b"
     r"|\bmitigate\b|\bdelays\b|\btarget\b|\blaunch day coordination\b", "Leadership"),
]


_WEEKDAY_TO_INT: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _next_weekday(anchor: date, weekday: int) -> date:
    delta = (weekday - anchor.weekday()) % 7
    if delta == 0:
        delta = 7
    return anchor + timedelta(days=delta)


# ─────────────────────────────────────────────────────────────────────────────
# Deadline extraction — ordered from most specific to most fuzzy
# ─────────────────────────────────────────────────────────────────────────────

def _guess_deadline(text: str, ctx: ToolContext) -> tuple[str | None, str | None]:
    t = text.strip()

    # ASAP / as soon as possible
    if re.search(r"\b(asap|as soon as possible)\b", t, flags=re.IGNORECASE):
        return "ASAP", "asap"

    # "within N weeks"
    m_weeks = re.search(r"\bwithin\s+(\d+)\s+weeks\b", t, flags=re.IGNORECASE)
    if m_weeks:
        w = int(m_weeks.group(1))
        d = ctx.meeting_date + timedelta(days=7 * w)
        return d.isoformat(), "within_weeks"

    # "within two weeks" / "within a week"
    m_words = re.search(r"\bwithin\s+(a|one|two|three|four)\s+weeks?\b", t, flags=re.IGNORECASE)
    if m_words:
        mapping = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4}
        w = mapping[m_words.group(1).lower()]
        d = ctx.meeting_date + timedelta(days=7 * w)
        return d.isoformat(), "within_weeks"

    # "within N hours"
    m48 = re.search(r"\bwithin\s+(\d+)\s+hours\b", t, flags=re.IGNORECASE)
    if m48:
        hrs = int(m48.group(1))
        dt = datetime.combine(ctx.meeting_date, datetime.min.time()) + timedelta(hours=hrs)
        return dt.strftime("%Y-%m-%d %H:%M"), "within_hours"

    # "tonight HH PM" / "tonight 8 PM"
    m_tonight = re.search(r"\btonight\s+(\d{1,2})(?:\s*:\s*(\d{2}))?\s*(am|pm)\b", t, flags=re.IGNORECASE)
    if m_tonight:
        hour = int(m_tonight.group(1))
        minute = int(m_tonight.group(2) or 0)
        ampm = m_tonight.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day, hour, minute).strftime("%Y-%m-%d %H:%M"), "tonight_time"

    # "tonight" without time → same day 20:00
    if re.search(r"\btonight\b", t, flags=re.IGNORECASE):
        return datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day, 20, 0).strftime("%Y-%m-%d %H:%M"), "tonight_default"

    # "tomorrow [at HH PM]"
    if re.search(r"\btomorrow\b", t, flags=re.IGNORECASE):
        d = ctx.meeting_date + timedelta(days=1)
        hm = re.search(r"\b(\d{1,2})\s*(:\s*(\d{2}))?\s*(am|pm)\b", t, flags=re.IGNORECASE)
        if hm:
            hour = int(hm.group(1))
            minute = int(hm.group(3) or 0)
            ampm = hm.group(4).lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return datetime(d.year, d.month, d.day, hour, minute).strftime("%Y-%m-%d %H:%M"), "tomorrow_time"
        return d.isoformat(), "tomorrow"

    # "by <date/weekday>"
    m_by = re.search(r"\bby\s+([^.,;\n]+)", t, flags=re.IGNORECASE)
    if m_by:
        chunk = m_by.group(1).strip()
        # weekday name first
        wd = re.match(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", chunk, flags=re.IGNORECASE)
        if wd:
            d = _next_weekday(ctx.meeting_date, _WEEKDAY_TO_INT[wd.group(1).lower()])
            return d.isoformat(), "by_weekday"
        try:
            default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
            dt = date_parser.parse(chunk, fuzzy=True, default=default_dt)
            if dt.time() != datetime.min.time():
                return dt.strftime("%Y-%m-%d %H:%M"), "by_datetime"
            return dt.date().isoformat(), "by_date"
        except Exception:
            return None, None

    # "before <date/weekday>"
    m_before = re.search(r"\bbefore\s+([^.,;\n]+)", t, flags=re.IGNORECASE)
    if m_before:
        chunk = m_before.group(1).strip()
        wd = re.match(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", chunk, flags=re.IGNORECASE)
        if wd:
            d = _next_weekday(ctx.meeting_date, _WEEKDAY_TO_INT[wd.group(1).lower()])
            return d.isoformat(), "before_weekday"
        try:
            default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
            dt = date_parser.parse(chunk, fuzzy=True, default=default_dt)
            return dt.date().isoformat(), "before_date"
        except Exception:
            return None, None

    # "starting <date/weekday>"
    m_start = re.search(r"\bstarting\s+([^.,;\n]+)", t, flags=re.IGNORECASE)
    if m_start:
        chunk = m_start.group(1).strip()
        wd = re.match(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", chunk, flags=re.IGNORECASE)
        if wd:
            d = _next_weekday(ctx.meeting_date, _WEEKDAY_TO_INT[wd.group(1).lower()])
            return d.isoformat(), "starting_weekday"
        try:
            default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
            dt = date_parser.parse(chunk, fuzzy=True, default=default_dt)
            return dt.date().isoformat(), "starting_date"
        except Exception:
            return None, None

    # "today" or "EOD" (only after we try parsing explicit "by ..." deadlines)
    if re.search(r"\btoday\b|\bEOD\b", t, flags=re.IGNORECASE):
        return ctx.meeting_date.isoformat(), "today_eod"

    # "around <date>" — used for approx dates like "around May 8th"
    m_around = re.search(r"\baround\s+([^.,;\n]+)", t, flags=re.IGNORECASE)
    if m_around:
        chunk = m_around.group(1).strip()
        try:
            default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
            dt = date_parser.parse(chunk, fuzzy=True, default=default_dt)
            return dt.date().isoformat(), "around_date"
        except Exception:
            return None, None

    # fuzzy date anywhere in text
    try:
        default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
        dt2 = date_parser.parse(t, fuzzy=True, default=default_dt)
        if dt2.date() != ctx.meeting_date:
            return dt2.date().isoformat(), "fuzzy_date"
    except Exception:
        pass
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Owner extraction — improved to handle summary-section patterns
# ─────────────────────────────────────────────────────────────────────────────

_INVALID_OWNER_WORDS = {
    "screens", "screenshots", "system", "build", "ui", "api",
    "backend", "frontend", "legal", "team", "development", "approval",
    "stable", "demo", "final", "updated", "marketing",
}

# Words that look like names but are really verbs / keywords in context
_FALSE_NAME_PATTERNS = re.compile(
    r"^(Prepare|Finalize|Share|Draft|Organize|Start|Complete|Implement|Set|Launch|"
    r"Deliver|Include|Approve|Review|Lock|Lead|Update|Add)$",
    flags=re.IGNORECASE,
)


def _clean_owner(candidate: str | None) -> str | None:
    if not candidate:
        return None
    c = candidate.strip().strip("@").strip()
    if not c:
        return None
    if c.lower() in _INVALID_OWNER_WORDS:
        return None
    if len(c) > 40:
        return None
    if _FALSE_NAME_PATTERNS.match(c):
        return None
    return c


def _guess_owner(text: str, speaker: str) -> str:
    t = text.strip()

    # Explicit first-person commitment → speaker is owner
    if re.search(r"^(i['']?ll|i will|let me|we['']?ll|we will|i can|i'll)\b", t, flags=re.IGNORECASE):
        return _clean_owner(speaker) or "Unassigned"

    # @mention
    m = re.search(r"\b(@[A-Za-z0-9_]+)\b", t)
    if m:
        mention: str = m.group(1)
        return _clean_owner(mention[1:]) or "Unassigned"

    # "Name will / can / should verb"
    m2 = re.search(r"\b([A-Z][a-z]+)\s+(will|can|should)\b", t)
    if m2:
        return _clean_owner(m2.group(1)) or "Unassigned"

    # "Name please verb" — e.g. "Bob please send the deck"
    m3 = re.match(r"^([A-Z][a-z]+)\s+(?:please|kindly)\s+", t)
    if m3:
        return _clean_owner(m3.group(1)) or "Unassigned"

    # "let's" / collective → attributed to speaker who suggested it
    if re.match(r"^let['']?s\b", t, flags=re.IGNORECASE):
        return _clean_owner(speaker) or "Unassigned"

    # "my team" → speaker
    if re.search(r"\bmy team\b", t, flags=re.IGNORECASE):
        return _clean_owner(speaker) or "Unassigned"

    # Summary-section heuristic: short imperative sentences beginning with an
    # action verb that have a deadline — attributed to the speaker who listed them.
    if re.search(r"\bby\b|\btomorrow\b|\bby\s+\w+\b|\bwithin\b|\bhours\b|\bdays\b|\bweeks\b|\btonight\b", t, flags=re.IGNORECASE):
        cleaned = _clean_owner(speaker)
        if cleaned:
            return cleaned

    return "Team"


def _classify_category(text: str) -> str:
    for pattern, label in _CATEGORY_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label
    return "Other"


# ─────────────────────────────────────────────────────────────────────────────
# Priority scoring — expanded keyword lists
# ─────────────────────────────────────────────────────────────────────────────

def _score_priority(item: ActionItem, ctx: ToolContext) -> tuple[int, str, list[str]]:
    score = 1
    txt = item.title.lower()
    hits: list[str] = []

    # Strategic / business urgency
    if any(k in txt for k in ["launch", "before launch", "q2", "april 30", "release", "may 15", "public launch"]):
        score += 3
        hits.append("strategic_launch")

    # Investor / external pressure
    if any(k in txt for k in ["investors", "traction", "review", "cannot happen", "can't happen"]):
        score += 2
        hits.append("external_pressure")

    # Deadline within 14 days from meeting date
    if item.deadline:
        try:
            d = date_parser.parse(item.deadline, fuzzy=True).date()
            days_out = (d - ctx.meeting_date).days
            if 0 <= days_out <= 7:
                score += 3
                hits.append("deadline_within_7d")
            elif 8 <= days_out <= 14:
                score += 2
                hits.append("deadline_within_14d")
            elif 15 <= days_out <= 30:
                score += 1
                hits.append("deadline_within_30d")
        except Exception:
            pass

    # Critical / urgency keywords
    if any(k in txt for k in [
        "critical", "no delays", "delays are not an option", "cannot afford", "urgent", "asap",
        "don't wait", "mitigate", "early", "cannot happen again",
    ]):
        score += 2
        hits.append("urgency_keywords")

    # Risk / blocking keywords
    if any(k in txt for k in ["risk", "scope creep", "freeze", "blocker", "blocked", "delay"]):
        score += 2
        hits.append("risk_blocking")

    # Dependency / approval signals
    if any(k in txt for k in ["blocked", "depends", "need final", "approval", "waiting", "without that"]):
        score += 1
        hits.append("dependency_signals")

    # External stakeholder impact
    if any(k in txt for k in ["legal", "enterprise", "clients", "externally", "apple", "apple sandbox"]):
        score += 1
        hits.append("external_stakeholders")

    # High confidence boosts score slightly
    if item.confidence_score >= 0.85:
        score += 1
        hits.append("high_confidence")

    score = max(1, min(10, score))
    if score >= 8:
        label = "P1"
    elif score >= 5:
        label = "P2"
    else:
        label = "P3"
    return score, label, hits


def task_classify(items: list[ActionItem], ctx: ToolContext) -> list[ActionItem]:
    validate_tool_call(ToolName.TASK_CLASSIFY.value)
    with TimeoutGuard(TOOL_TIMEOUT_SECONDS, ToolName.TASK_CLASSIFY.value):
        out: list[ActionItem] = []
        for it in items:
            txt = it.title
            owner = it.owner
            if not owner or owner == "Unassigned":
                owner = _guess_owner(txt, it.source_speakers[0] if it.source_speakers else "Unassigned")

            deadline = it.deadline
            method = it.deadline_parse_method
            if not deadline:
                deadline, method = _guess_deadline(txt, ctx)
            cat = _classify_category(txt)
            out.append(it.model_copy(update={"category": cat, "owner": owner, "deadline": deadline, "deadline_parse_method": method}))
        return out

    raise RuntimeError("unreachable")


def priority_score(items: list[ActionItem], ctx: ToolContext) -> list[ActionItem]:
    validate_tool_call(ToolName.PRIORITY_SCORE.value)
    with TimeoutGuard(TOOL_TIMEOUT_SECONDS, ToolName.PRIORITY_SCORE.value):
        out: list[ActionItem] = []
        for it in items:
            score, label, hits = _score_priority(it, ctx)
            out.append(it.model_copy(update={"priority_score": score, "priority_label": label, "priority_rule_hits": hits}))
        out.sort(key=lambda x: (-int(x.priority_score), x.title))
        return out

    raise RuntimeError("unreachable")


def meeting_summarize(raw_text: str, items: list[ActionItem], ctx: ToolContext) -> dict[str, Any]:
    validate_tool_call(ToolName.MEETING_SUMMARIZE.value)
    with TimeoutGuard(TOOL_TIMEOUT_SECONDS, ToolName.MEETING_SUMMARIZE.value):
        return generate_analysis(raw_text, items, meeting_date=ctx.meeting_date)

    raise RuntimeError("unreachable")


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy deduplication — normalized title similarity
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Remove common filler prefixes that differ between summary/original
    s = re.sub(r"^(please |action item:?\s*|i'll |i will |we'll |we will )", "", s)
    return s


def _title_overlap(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two normalized titles."""
    wa = set(a.split())
    wb = set(b.split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _title_containment(a: str, b: str) -> float:
    wa = set(a.split())
    wb = set(b.split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def deduplicate(items: list[ActionItem]) -> list[ActionItem]:
    validate_tool_call(ToolName.DEDUPLICATE.value)
    # Exact-key deduplication first
    kept: list[ActionItem] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for it in items:
        desc = _normalize_title(it.title)
        key = (it.owner.strip().lower(), (it.deadline or "").strip().lower(), desc)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        kept.append(it)

    # Fuzzy deduplication — remove items that are >=75% word-overlap with a kept item
    # and share the same owner+deadline bucket, OR >=50% overlap regardless of owner
    # (catches cases where the owner was mis-assigned on one but not the other).
    final: list[ActionItem] = []
    norm_final: list[str] = []
    for it in kept:
        nt = _normalize_title(it.title)
        # Filter out very short / vague titles (fewer than 3 words)
        if len(nt.split()) < 3:
            continue
        is_dup = False
        for idx_f, existing_nt in enumerate(norm_final):
            existing: ActionItem = final[idx_f]
            overlap = _title_overlap(nt, existing_nt)
            containment = _title_containment(nt, existing_nt)
            # Same owner+deadline: 75% threshold or 80% containment
            same_owner = it.owner == existing.owner
            same_dl = (it.deadline or "") == (existing.deadline or "")
            if same_owner and same_dl and (overlap >= 0.75 or containment >= 0.80):
                is_dup = True
                break
            # Cross-owner: higher bar (50% overlap) — catches duplicates
            # where the same task was phrased differently by two speakers
            if overlap >= 0.50:
                is_dup = True
                break
        if not is_dup:
            final.append(it)
            norm_final.append(nt)
    return final


# ─────────────────────────────────────────────────────────────────────────────
# Confidence scoring
# ─────────────────────────────────────────────────────────────────────────────

_HIGH_CONF_PATTERNS = [
    r"\baction item\b",
    r"\btodo\b",
    r"\bto-do\b",
    r"\bplease\b.*\bby\b",
    # Summary-recap items: short imperative with deadline
]

_MED_CONF_PATTERNS = [
    r"^(i['']?ll|we['']?ll|complete|provide|share|send|finalize|update|organize|"
    r"prepare|review|draft|collaborate|set up|deliver|implement|start|approve|lock)\b",
    r"\bwill\b.*\bby\b",
    r"\bwill\b.*\btomorrow\b",
    r"\bwill\b.*\bEOD\b",
    r"\bwe need to\b",
    r"\blet['']?s\b",
    r"\blets\b",
]


def _calc_confidence(text: str) -> float:
    for pat in _HIGH_CONF_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return 0.9
    for pat in _MED_CONF_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return 0.65
    return 0.4


# ─────────────────────────────────────────────────────────────────────────────
# Action item extraction — handles both conversational and summary-section text
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that signal an explicit action item (high confidence)
_EXPLICIT_PATTERNS = [
    r"\b(action item|todo|to-do)\b",
    r"\bwe need to\b",
    r"\bwe should\b",
    r"\bsomeone needs to\b",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bplease\b",
    r"\bplease\s+\w+\b",
    r"\blet's\b",
    r"\blets\b",
]

# Patterns that signal an implicit commitment (medium confidence)
_IMPLICIT_START_PATTERNS = re.compile(
    r"^(i\s+will|i['’]?ll|i\s+can|we\s+will|we['’]?ll|we\s+can|complete|provide|share|send|"
    r"finalize|update|organize|prepare|review|draft|collaborate|set up|deliver|implement|"
    r"start|approve|lock)\b",
    flags=re.IGNORECASE,
)

# Short imperative with deadline — common in recap/summary sections
_IMPERATIVE_WITH_DEADLINE = re.compile(
    r"^(finalize|prepare|share|draft|organize|deliver|set up|implement|start|"
    r"approve|lock|lead|update|include|review|complete)\b.{5,}"
    r".*(by |tonight|tomorrow|around|within|march|april|may|monday|tuesday|wednesday|thursday|friday)\b",
    flags=re.IGNORECASE,
)


def _clean_task_title(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^action item\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^todo\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^to-?do\s*:\s*", "", s, flags=re.IGNORECASE)

    # Remove direct @mentions / leading names (delegate cue often handled separately)
    s = re.sub(r"^@([A-Za-z][A-Za-z0-9_\-]{1,30})\b[,:]?\s*", "", s)
    s = re.sub(r"^([A-Z][a-z]+)\b[,:]\s+", "", s)
    # "Bob please send..." → strip name + please
    s = re.sub(r"^([A-Z][a-z]+)\s+(?:please|kindly)\s+", "", s)

    s = re.sub(r"^please\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(can|could)\s+you\s+", "", s, flags=re.IGNORECASE)

    s = re.sub(r"^we\s+need\s+to\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^we\s+should\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^someone\s+needs\s+to\s+", "", s, flags=re.IGNORECASE)

    s = re.sub(r"^i\s+will\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^i['’]?ll\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^i\s+can\s+", "", s, flags=re.IGNORECASE)

    s = re.sub(r"^i\s+will\s+be\s+able\s+to\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^we['’]?ll\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^we\s+will\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^we\s+can\s+", "", s, flags=re.IGNORECASE)

    # "let's" → keep the rest as the task
    s = re.sub(r"^let['\u2019]?s\s+", "", s, flags=re.IGNORECASE)

    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[.?!]+$", "", s).strip()

    if s:
        s = s[0].upper() + s[1:]
    return s


def _remove_deadline_phrases(text: str) -> str:
    s = text
    s = re.sub(r"\s+by\s+([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+by\s+(tomorrow|today|tonight)\b(?:\s+(noon|eod|end of day|morning|afternoon|evening))?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(tomorrow|today|tonight)\b(?:\s+(noon|eod|end of day|morning|afternoon|evening))?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?:\s+(eod|end of day|noon|morning))?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+next\s+week\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+within\s+\d+\s+days\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+before\s+(launch|release|we\s+ship|shipping|testing\s+finishes)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+after\s+(testing|launch|release)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_action_items(transcript: Transcript, ctx: ToolContext) -> list[ActionItem]:
    validate_tool_call(ToolName.EXTRACT_ACTION_ITEMS.value)
    with TimeoutGuard(TOOL_TIMEOUT_SECONDS, ToolName.EXTRACT_ACTION_ITEMS.value):
        items: list[ActionItem] = []
        # noinspection PyTypeChecker
        idx: int = 1
        for turn in transcript.turns:
            txt = turn.text.strip()
            candidates: list[tuple[str, float]] = []  # (sentence, confidence)

            chunks: list[str] = []
            for ln in txt.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                for sent in re.split(r"(?<=[.!?])\s+", ln):
                    s2 = sent.strip()
                    if s2:
                        chunks.append(s2)

            for sent in chunks:
                s = sent.strip()
                if not s or len(s) < 8:
                    continue

                if _looks_like_non_task(s):
                    continue

                # Explicit trigger keyword (highest confidence)
                if any(re.search(p, s, flags=re.IGNORECASE) for p in _EXPLICIT_PATTERNS):
                    if _has_action_verb(s) or _IMPLICIT_START_PATTERNS.match(s):
                        candidates.append((s, 0.9))
                    continue

                # First-person / standard commitment opener
                if _IMPLICIT_START_PATTERNS.match(s):
                    candidates.append((s, 0.65))
                    continue

                # Requirement / obligation phrasing (must/needs to/need to)
                if re.search(r"\bmust\b|\bneeds\s+to\b|\bneed\s+to\b|\bhas\s+to\b", s, flags=re.IGNORECASE):
                    if _has_action_verb(s):
                        candidates.append((s, 0.65))
                    continue

                # "X will ... by Y" pattern
                if re.search(r"\bwill\b", s, flags=re.IGNORECASE) and re.search(
                    r"\bby\b|\btomorrow\b|\bnext\s+week\b|\bEOD\b|\btonight\b",
                    s, flags=re.IGNORECASE,
                ):
                    if _has_action_verb(s):
                        candidates.append((s, 0.65))
                    continue

                # Short imperative with a concrete deadline → summary-section item
                if _IMPERATIVE_WITH_DEADLINE.match(s):
                    candidates.append((s, 0.85))

            seen: set[str] = set()
            for c, conf in candidates:
                key = re.sub(r"\s+", " ", c.strip().lower())
                if key in seen:
                    continue
                seen.add(key)

                owner = _infer_owner_from_sentence(c, turn.speaker)

                deadline, method = _guess_deadline(c, ctx)
                cleaned = _clean_task_title(c)
                if deadline:
                    cleaned = _remove_deadline_phrases(cleaned)
                cleaned = cleaned.strip()
                if not cleaned:
                    cleaned = _clean_task_title(c)

                items.append(
                    ActionItem(
                        id=f"T{idx:03d}",
                        title=cleaned,
                        owner=owner,
                        deadline=deadline,
                        deadline_parse_method=method,
                        source_speakers=[turn.speaker],
                        confidence_score=conf,
                    )
                )
                idx += 1  # type: ignore[operator]
        return items

    raise RuntimeError("unreachable")
