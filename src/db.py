from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class PastRun(Base):
    __tablename__ = "past_runs"

    id = Column(Integer, primary_key=True)
    username = Column(String, index=True)
    run_id = Column(String, unique=True, index=True)
    meeting_date = Column(String)
    raw_transcript = Column(String)
    tasks_json = Column(String)
    analysis_json = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine("sqlite:///meetings.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def save_run(username: str, run_id: str, meeting_date: str, raw_transcript: str, tasks: list[Any], analysis: dict[str, Any]) -> None:
    session = SessionLocal()
    try:
        run = PastRun(
            username=username,
            run_id=run_id,
            meeting_date=meeting_date,
            raw_transcript=raw_transcript,
            tasks_json=json.dumps(tasks),
            analysis_json=json.dumps(analysis),
        )
        session.add(run)
        session.commit()
    finally:
        session.close()


def get_runs_for_user(username: str) -> list[dict[str, Any]]:
    session = SessionLocal()
    try:
        runs_db = session.query(PastRun).filter(PastRun.username == username).order_by(PastRun.created_at.desc()).all()
        runs = []
        for r in runs_db:
            runs.append({
                "run_id": r.run_id,
                "meeting_date": r.meeting_date,
                "raw_transcript": r.raw_transcript,
                "tasks": json.loads(r.tasks_json),
                "analysis": json.loads(r.analysis_json),
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
            })
        return runs
    finally:
        session.close()
