from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from dateutil import parser as date_parser

from .schemas import ActionItem, Transcript, TranscriptTurn
from .tools import ToolContext


@dataclass
class SingleAgentBaseline:
    """A single-pass baseline that extracts, classifies, and scores in one go without structured agents."""

    def run(self, raw_text: str, ctx: ToolContext) -> list[ActionItem]:
        turns = self._split_turns(raw_text)
        items = self._extract_items(turns)
        items = self._classify_items(items, ctx)
        items = self._score_items(items, ctx)
        return items

    def _split_turns(self, raw: str) -> list[TranscriptTurn]:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        turns: list[TranscriptTurn] = []
        current_speaker = "Unknown"
        buf: list[str] = []

        def flush() -> None:
            nonlocal buf
            if buf:
                turns.append(TranscriptTurn(speaker=current_speaker, text=" ".join(buf).strip()))
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

    def _extract_items(self, turns: list[TranscriptTurn]) -> list[ActionItem]:
        items: list[ActionItem] = []
        idx = 1
        for turn in turns:
            txt = turn.text.strip()
            candidates: list[str] = []
            for sent in re.split(r"(?<=[.!?])\s+", txt):
                s = sent.strip()
                if not s:
                    continue
                if re.search(r"\b(action item|todo|to-do|we need to|please|let's|lets)\b", s, flags=re.IGNORECASE):
                    candidates.append(s)
                elif re.search(r"^(i['’]?ll|we['’]?ll|complete|provide|share|send|finalize|update|organize|prepare|review|draft|collaborate)\b", s, flags=re.IGNORECASE):
                    candidates.append(s)
                elif re.search(r"\bwill\b", s, flags=re.IGNORECASE) and re.search(r"\bby\b|\btomorrow\b|\bnext\s+week\b|\bEOD\b", s, flags=re.IGNORECASE):
                    candidates.append(s)

            seen: set[str] = set()
            for c in candidates:
                key = re.sub(r"\s+", " ", c.strip().lower())
                if key in seen:
                    continue
                seen.add(key)

                items.append(
                    ActionItem(
                        id=f"T{idx:03d}",
                        title=c,
                        deadline=None,
                        source_speakers=[turn.speaker],
                    )
                )
                idx += 1  # type: ignore[operator]
        return items

    def _classify_items(self, items: list[ActionItem], ctx: ToolContext) -> list[ActionItem]:
        _CATEGORY_RULES = [
            (r"\bapi\b|\bbackend\b|\bfrontend\b|\bengineering\b|\bqa\b|\bbuild\b|\bdeploy\b|\bstable build\b", "Engineering"),
            (r"\bfeature\b|\bscope\b|\bproduct\b|\banalytics\b|\bwidgets\b|\bmockups\b|\bdesign\b", "Product"),
            (r"\blaunch\b|\bemail\b|\blanding page\b|\bdemo video\b|\bcopy\b|\bcampaign\b", "Marketing"),
            (r"\bpricing\b|\bsales\b|\benterprise\b|\benablement\b|\bdeck\b|\bclients\b", "Sales"),
            (r"\bonboarding\b|\boperations\b|\bdocs\b|\bdocumentation\b|\btraining\b", "Operations"),
            (r"\bsupport\b|\bcustomer\b", "Customer Success"),
            (r"\bapprove\b|\breview\b|\bfreeze\b|\brisk\b|\bcritical\b|\bno delays\b", "Leadership"),
        ]

        def _guess_deadline(text: str) -> str | None:
            m = re.search(r"\bby\s+([^.,;\n]+)", text, flags=re.IGNORECASE)
            if not m:
                return None
            chunk = m.group(1).strip()
            try:
                default_dt = datetime(ctx.meeting_date.year, ctx.meeting_date.month, ctx.meeting_date.day)
                dt = date_parser.parse(chunk, fuzzy=True, default=default_dt)
                if dt.time() != datetime.min.time():
                    return dt.strftime("%Y-%m-%d %H:%M")
                return dt.date().isoformat()
            except Exception:
                return None

        def _guess_owner(text: str, speaker: str) -> str:
            if re.search(r"^(i['’]?ll|i will|let me|we['’]?ll|we will)\b", text, flags=re.IGNORECASE):
                return speaker
            m = re.search(r"\b(@[A-Za-z0-9_]+)\b", text)
            if m:
                mention: str = m.group(1)
                return mention[1:]
            m2 = re.search(r"\b([A-Z][a-z]+)\s+(will|can|should)\b", text)
            if m2:
                return m2.group(1)
            return "Unassigned"

        out: list[ActionItem] = []
        for it in items:
            txt = it.title
            cat = "Other"
            for pattern, label in _CATEGORY_RULES:
                if re.search(pattern, txt, flags=re.IGNORECASE):
                    cat = label
                    break
            owner = _guess_owner(txt, it.source_speakers[0] if it.source_speakers else "Unassigned")
            deadline = _guess_deadline(txt)
            out.append(it.model_copy(update={"category": cat, "owner": owner, "deadline": deadline}))
        return out

    def _score_items(self, items: list[ActionItem], ctx: ToolContext) -> list[ActionItem]:
        out: list[ActionItem] = []
        for it in items:
            score = 1
            txt = it.title.lower()
            if any(k in txt for k in ["launch", "before launch", "q2", "april 30", "release"]):
                score += 3
            if it.deadline:
                try:
                    d = date_parser.parse(it.deadline, fuzzy=True).date()
                    if 0 <= (d - ctx.meeting_date).days <= 14:
                        score += 2
                except Exception:
                    pass
            if any(k in txt for k in ["critical", "no delays", "can't afford", "cannot afford", "urgent", "asap"]):
                score += 2
            if any(k in txt for k in ["risk", "mitigate", "scope creep", "freeze"]):
                score += 2
            if any(k in txt for k in ["blocked", "blocker", "depends", "need final", "approval"]):
                score += 1
            if any(k in txt for k in ["legal", "enterprise", "clients", "externally"]):
                score += 1
            score = max(1, min(10, score))
            label = "P1" if score >= 8 else "P2" if score >= 5 else "P3"
            out.append(it.model_copy(update={"priority_score": score, "priority_label": label}))
        out.sort(key=lambda x: (-int(x.priority_score), x.title))
        return out
