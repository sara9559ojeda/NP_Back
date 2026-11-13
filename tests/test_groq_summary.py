import json
import re
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.ai.groq_summary import SummaryRejected, fingerprint, make_facts, request_summary

SETTINGS = SimpleNamespace(groq_model="openai/gpt-oss-20b", groq_api_key=SecretStr("test-key"))

# Answer returned by the real provider in production on 12-11-2026 for a session that ended at level 5
# with the distress going UP by ten points (sudsDrop = -10). It copies the numeric facts and misreads the sign.
PRODUCTION_OUTPUT_V1 = (
    "El usuario alcanzó el nivel 5 durante 500.3265 segundos y terminó la sesión por decisión propia. "
    "Los indicadores técnicos mostraron que el criterio no se cumplió, con un descenso de SUDS de 10 y 60 "
    "después, y 12 conteos de evitación. Se recomienda dar un paso atrás y esperar revisión profesional."
)


def provider(content, finish="stop"):
    def respond(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {"content": content}}]})
    return httpx.Client(transport=httpx.MockTransport(respond))


def production_like_facts(sudsDrop=-10, avoidance=12, level=5, extra=()):
    session = SimpleNamespace(level_reached=level, total_duration_seconds=500.3265, end_reason="user_finished")
    basis = [{"feature": "criterionMet", "value": False, "effect": "unfavorable"},
             {"feature": "avoidanceCount", "value": avoidance, "effect": "unfavorable"}]
    if sudsDrop is not None:
        basis += [{"feature": "sudsDrop", "value": sudsDrop, "effect": "unfavorable"},
                  {"feature": "sudsAfter", "value": 60, "effect": "unfavorable"}]
    basis += list(extra)
    return make_facts(session, "step_back", 0.232, basis, evaluated_level=level, evaluated_attempt=1,
                      method="rules-baseline", method_version="0.1.0")


@pytest.mark.parametrize("content,finish", [
    ({"summary": "Has mejorado un 80 por ciento.", "recommendation": "repeat"}, "stop"),
    ({"summary": "Una explicación con <b>contenido</b> no permitido.", "recommendation": "repeat"}, "stop"),
    ({"summary": "La recomendación técnica indica repetir el nivel evaluado.", "recommendation": "advance"}, "stop"),
    ({"summary": "La recomendación técnica indica repetir el nivel evaluado.", "recommendation": "repeat"}, "length"),
])
def test_invalid_or_incomplete_generated_text_is_rejected(content, finish):
    with provider(json.dumps(content), finish) as client, pytest.raises(ValueError):
        request_summary({"recommendation": "repeat"}, SETTINGS, client)


@pytest.mark.parametrize("content,finish,reason", [
    (json.dumps({"summary": PRODUCTION_OUTPUT_V1, "recommendation": "step_back"}), "stop", "unsupported_content"),
    (json.dumps({"summary": "La sesión termina con una orientación técnica distinta.", "recommendation": "advance"}), "stop", "recommendation_changed"),
    (json.dumps({"summary": "La sesión registra el criterio del nivel evaluado.", "recommendation": "step_back"}), "length", "incomplete"),
    ("esto no es JSON", "stop", "schema"),
    (json.dumps({"summary": "corto", "recommendation": "step_back"}), "stop", "schema"),
])
def test_rejections_report_a_fixed_reason_without_the_text(content, finish, reason):
    with provider(content, finish) as client, pytest.raises(SummaryRejected) as rejected:
        request_summary({"recommendation": "step_back"}, SETTINGS, client)
    assert rejected.value.reason == reason
    assert str(rejected.value) == reason


def test_malformed_provider_body_is_rejected():
    def respond(request):
        return httpx.Response(200, json={"choices": []})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(SummaryRejected) as rejected:
        request_summary({"recommendation": "repeat"}, SETTINGS, client)
    assert rejected.value.reason == "malformed"


def test_facts_sent_to_the_provider_contain_no_digits():
    facts = production_like_facts(extra=[{"feature": "safeExit", "value": True, "effect": "unfavorable"}])
    assert not re.search(r"\d", json.dumps(facts, ensure_ascii=False))
    assert facts == {
        "evaluatedLevel": "final_level",
        "endReason": "user_finished",
        "recommendation": "step_back",
        "criterionMet": False,
        "selfReportedDistress": "increased",
        "avoidanceEvents": "recorded",
        "safeExit": True,
        "clinicalStatus": "pending_professional_review",
        "method": "rules-baseline",
    }


@pytest.mark.parametrize("sudsDrop,expected", [(-10, "increased"), (20, "decreased"), (0, "unchanged"), (None, "not_reported")])
def test_distress_direction_follows_the_sign_of_suds_drop(sudsDrop, expected):
    assert production_like_facts(sudsDrop=sudsDrop)["selfReportedDistress"] == expected


@pytest.mark.parametrize("level,expected", [(1, "first_level"), (3, "intermediate_level"), (5, "final_level")])
def test_level_is_described_by_position(level, expected):
    assert production_like_facts(level=level)["evaluatedLevel"] == expected


def test_no_avoidance_is_described_as_none():
    assert production_like_facts(avoidance=0)["avoidanceEvents"] == "none"


def test_fingerprint_changes_with_numeric_analysis_inputs_not_sent_to_the_provider():
    facts = production_like_facts()
    base = fingerprint(facts, "openai/gpt-oss-20b", True, {"technicalIndex": 0.232})
    assert base == fingerprint(facts, "openai/gpt-oss-20b", True, {"technicalIndex": 0.232})
    assert base != fingerprint(facts, "openai/gpt-oss-20b", True, {"technicalIndex": 0.4})
    assert base != fingerprint(facts, "openai/gpt-oss-20b", False, {"technicalIndex": 0.232})
