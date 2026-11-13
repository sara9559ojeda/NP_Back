import asyncio
import logging
from datetime import timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.groq_summary import SummaryRejected, enabled, make_facts, request_summary
from app.core.config import get_settings
from app.core.security import utcnow
from app.db.models import Analysis, NarrativeUsage, TherapySession
from app.db.session import get_engine

logger = logging.getLogger("neurophobia.narratives")


def provider_client(settings):
    return httpx.Client(timeout=settings.groq_timeout_seconds, follow_redirects=False, trust_env=False)


def failure_reason(exc: Exception) -> str:
    """Fixed category for the log; never the provider text or the request."""
    if isinstance(exc, SummaryRejected):
        return exc.reason
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "network"
    return type(exc).__name__


def reserve_daily_request(db: Session, limit: int) -> bool:
    if limit <= 0:
        return False
    statement = insert(NarrativeUsage).values(day=utcnow().date(), requests=1)
    statement = statement.on_conflict_do_update(
        index_elements=["day"],
        set_={"requests": NarrativeUsage.requests + 1},
        where=NarrativeUsage.requests < limit,
    ).returning(NarrativeUsage.requests)
    return db.execute(statement).scalar_one_or_none() is not None


def process_next_summary() -> bool:
    settings = get_settings()
    if not enabled(settings):
        return False
    started_at = utcnow()
    with Session(get_engine(), expire_on_commit=False) as db:
        analysis = db.scalars(
            select(Analysis).where(or_(
                Analysis.narrative_status == "pending",
                (Analysis.narrative_status == "generating") & (Analysis.narrative_started_at < started_at - timedelta(minutes=2)),
            )).order_by(Analysis.created_at).with_for_update(skip_locked=True).limit(1)
        ).first()
        if analysis is None:
            return False
        session = db.get(TherapySession, analysis.session_id)
        if session is None or not (session.has_start and session.has_end) or session.test_session is not False:
            analysis.narrative_status = "fallback"
            db.commit()
            return True
        if not reserve_daily_request(db, settings.groq_daily_request_limit):
            analysis.narrative_status = "quota_exceeded"
            db.commit()
            return True
        analysis.narrative_status = "generating"
        analysis.narrative_started_at = started_at
        facts = make_facts(
            session, analysis.recommendation, analysis.tolerance_index, analysis.basis,
            evaluated_level=analysis.evaluated_level, evaluated_attempt=analysis.evaluated_attempt,
            method=analysis.method, method_version=analysis.method_version,
        )
        identity = (analysis.session_id, analysis.method, analysis.input_fingerprint)
        db.commit()

    status, narrative = "fallback", None
    try:
        with provider_client(settings) as client:
            narrative = request_summary(facts, settings, client)
        status = "generated"
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Optional session summary unavailable (%s); deterministic explanation retained", failure_reason(exc))

    with Session(get_engine()) as db:
        db.execute(
            update(Analysis).where(
                Analysis.session_id == identity[0],
                Analysis.method == identity[1],
                Analysis.input_fingerprint == identity[2],
                Analysis.narrative_started_at == started_at,
                Analysis.narrative_status == "generating",
            ).values(narrative_text=narrative, narrative_status=status, narrative_created_at=utcnow())
        )
        db.commit()
    return True


async def summary_worker() -> None:
    while True:
        try:
            processed = await run_in_threadpool(process_next_summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Summary worker iteration failed (%s)", type(exc).__name__)
            processed = False
        await asyncio.sleep(0.2 if processed else 3)
