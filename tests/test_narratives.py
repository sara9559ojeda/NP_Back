import json
from concurrent.futures import ThreadPoolExecutor

import httpx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Analysis, NarrativeUsage
from app.db.session import get_engine
from app.services import narratives
from tests.conftest import API, envelope, full_session


def configure_provider(monkeypatch, handler, limit=25):
    settings = get_settings()
    monkeypatch.setattr(settings, "external_ai_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(settings, "groq_daily_request_limit", limit)
    monkeypatch.setattr(narratives, "provider_client", lambda settings: httpx.Client(transport=httpx.MockTransport(handler)))


def provider_response(request):
    facts = json.loads(json.loads(request.content)["messages"][1]["content"])
    text = {"summary": "Los registros permiten revisar el criterio del nivel y la recomendación técnica.", "recommendation": facts["recommendation"]}
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(text)}}]})


def test_summary_is_saved_once_and_shared_with_headset(client, api, care_team, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return provider_response(request)
    configure_provider(monkeypatch, handler)
    sid = full_session(api, care_team["device"])
    assert narratives.process_next_summary()
    assert not narratives.process_next_summary()
    assert len(calls) == 1
    wire = json.loads(calls[0].content)
    assert wire["model"] == get_settings().groq_model
    assert sid not in calls[0].content.decode()
    assert "@" not in calls[0].content.decode()
    web = client.get(f"{API}/me/therapy", headers=care_team["patient_headers"]).json()["lastFeedback"]
    headset = client.get(f"{API}/device/context", headers=care_team["device"]).json()["lastFeedback"]
    assert web["analysis"]["narrativeStatus"] == "generated"
    assert web["analysis"]["narrative"] == headset["analysis"]["narrative"]
    assert web["analysis"]["explanation"]


def test_provider_quota_failure_keeps_rules_and_does_not_retry(client, api, care_team, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": "quota"})
    configure_provider(monkeypatch, handler)
    full_session(api, care_team["device"])
    assert narratives.process_next_summary()
    assert not narratives.process_next_summary()
    data = client.get(f"{API}/me/therapy", headers=care_team["patient_headers"]).json()["lastFeedback"]["analysis"]
    assert data["narrativeStatus"] == "fallback"
    assert data["narrative"] is None and data["explanation"]
    assert len(calls) == 1


def test_late_records_do_not_allow_a_stale_summary_to_overwrite_new_analysis(client, api, care_team, monkeypatch):
    sid = None
    def handler(request):
        api.send(care_team["device"], envelope("level_record", sid, level=3))
        return provider_response(request)
    configure_provider(monkeypatch, handler)
    sid = full_session(api, care_team["device"])
    assert narratives.process_next_summary()
    with Session(get_engine()) as db:
        result = db.scalars(select(Analysis)).one()
        assert result.narrative_status == "pending"
        assert result.narrative_text is None


def test_daily_limit_is_shared_and_atomic(app):
    def reserve(_):
        with Session(get_engine()) as db:
            granted = narratives.reserve_daily_request(db, 2)
            db.commit()
            return granted
    with ThreadPoolExecutor(max_workers=6) as pool:
        granted = list(pool.map(reserve, range(6)))
    assert sum(granted) == 2
    with Session(get_engine()) as db:
        assert db.scalars(select(NarrativeUsage.requests)).one() == 2


def test_request_limit_uses_deterministic_fallback(client, api, care_team, monkeypatch):
    def handler(request):
        raise AssertionError("Provider must not be called")
    configure_provider(monkeypatch, handler, limit=0)
    full_session(api, care_team["device"])
    assert narratives.process_next_summary()
    with Session(get_engine()) as db:
        assert db.scalars(select(Analysis.narrative_status)).one() == "quota_exceeded"
