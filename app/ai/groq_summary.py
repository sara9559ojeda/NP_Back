import hashlib
import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings

# v2: the model receives qualitative facts without any digit. With v1 it copied the numeric facts
# ("nivel 5", "500.3265 segundos"), every summary failed the content check and it also misread the
# sign of sudsDrop (a rise in distress was described as a drop).
PROMPT_VERSION = "session-summary-2"
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM_PROMPT = (
    "Write a short Spanish summary of an academic VR session using ONLY the supplied technical facts. "
    "Explain the existing recommendation; never change it or make a clinical decision. "
    "Do not diagnose, infer emotions, claim clinical improvement, give treatment advice, or invent observations. "
    "Do not include names, identifiers, digits or quantities, links, HTML, or Markdown: describe each fact in words, "
    "exactly as qualified in the facts. "
    "selfReportedDistress says whether the distress the person reported after the level increased, decreased or stayed "
    "the same compared with before; not_reported means insufficient self-report, not improvement. "
    "Use at most three short sentences. Return the requested JSON object."
)
UNSUPPORTED_CONTENT = re.compile(r"[\d<>]|https?://|diagn[oó]stic|curad[oa]|mejor[ií]a cl[ií]nica|superad[oa].*fobia", re.IGNORECASE)

RejectionReason = Literal["too_large", "invalid_json", "malformed", "incomplete", "schema", "recommendation_changed", "unsupported_content"]


class SummaryRejected(ValueError):
    """The provider answered but its text cannot be shown. ``reason`` is a fixed category, never the text."""

    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason)
        self.reason = reason


class GeneratedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=20, max_length=1000)
    recommendation: Literal["advance", "repeat", "step_back"]


def enabled(settings: Settings) -> bool:
    return bool(settings.external_ai_enabled and settings.groq_api_key and settings.groq_api_key.get_secret_value().strip())


def _level_position(level: int | None) -> str:
    if level is None:
        return "unknown"
    if level <= 1:
        return "first_level"
    return "final_level" if level >= 5 else "intermediate_level"


def _distress(values: dict) -> str:
    # sudsDrop = SUDS before - SUDS after: a negative value means the reported distress went UP.
    drop = values.get("sudsDrop")
    if drop is None:
        return "not_reported"
    return "decreased" if drop > 0 else "increased" if drop < 0 else "unchanged"


def make_facts(session, recommendation: str, tolerance_index: float, basis: list[dict], *, evaluated_level: int, evaluated_attempt: int, method: str, method_version: str) -> dict:
    """Facts sent to the provider. They contain no digit, so the summary has nothing to copy.

    The numeric values (level, duration, index, SUDS, counts) stay in the rules explanation shown next to it.
    """
    values = {item["feature"]: item["value"] for item in basis}
    facts = {
        "evaluatedLevel": _level_position(evaluated_level),
        "endReason": session.end_reason or "unknown",
        "recommendation": recommendation,
        "criterionMet": bool(values["criterionMet"]) if "criterionMet" in values else None,
        "selfReportedDistress": _distress(values),
        "avoidanceEvents": "recorded" if values.get("avoidanceCount") else "none",
        "safeExit": bool(values.get("safeExit", False)),
        "clinicalStatus": "pending_professional_review",
        "method": method,
    }
    return facts


def fingerprint(facts: dict, model: str, active: bool, analysis: dict | None = None) -> str:
    """Identity of a summary. ``analysis`` holds the numeric analysis inputs that are NOT sent to the provider:
    any change in them (late records, new method version) still resets the summary, as before."""
    payload = {"facts": facts, "analysis": analysis, "model": model, "active": active, "promptVersion": PROMPT_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def request_summary(facts: dict, settings: Settings, client: httpx.Client) -> str:
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "recommendation": {"type": "string", "enum": [facts["recommendation"]]},
        },
        "required": ["summary", "recommendation"],
        "additionalProperties": False,
    }
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "session_summary", "strict": True, "schema": schema}},
        "max_completion_tokens": 512,
        "temperature": 0.2,
        "stream": False,
    }
    if settings.groq_model.startswith("openai/gpt-oss-"):
        payload["reasoning_effort"] = "low"
    with client.stream("POST", ENDPOINT, json=payload, headers={"Authorization": f"Bearer {settings.groq_api_key.get_secret_value()}"}) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            body.extend(chunk)
            if len(body) > 65536:
                raise SummaryRejected("too_large")
    try:
        data = json.loads(body)
    except ValueError:
        raise SummaryRejected("invalid_json") from None
    try:
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason")
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError):
        raise SummaryRejected("malformed") from None
    if finish_reason != "stop":
        raise SummaryRejected("incomplete")
    try:
        result = GeneratedText.model_validate_json(content)
    except (ValidationError, TypeError):
        raise SummaryRejected("schema") from None
    if result.recommendation != facts["recommendation"]:
        raise SummaryRejected("recommendation_changed")
    if UNSUPPORTED_CONTENT.search(result.summary):
        raise SummaryRejected("unsupported_content")
    return result.summary.strip()
