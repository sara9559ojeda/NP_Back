import hashlib
import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings

PROMPT_VERSION = "session-summary-1"
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM_PROMPT = (
    "Write a short Spanish summary of an academic VR session using ONLY the supplied technical facts. "
    "Explain the existing recommendation; never change it or make a clinical decision. "
    "Do not diagnose, infer emotions, claim clinical improvement, give treatment advice, or invent observations. "
    "Do not include names, identifiers, numbers, links, HTML, or Markdown. "
    "Use at most three short sentences. Missing SUDS means insufficient self-report, not improvement. "
    "Return the requested JSON object."
)


class GeneratedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=20, max_length=1000)
    recommendation: Literal["advance", "repeat", "step_back"]


def enabled(settings: Settings) -> bool:
    return bool(settings.external_ai_enabled and settings.groq_api_key and settings.groq_api_key.get_secret_value().strip())


def make_facts(session, recommendation: str, tolerance_index: float, basis: list[dict], *, evaluated_level: int, evaluated_attempt: int, method: str, method_version: str) -> dict:
    return {
        "levelReached": session.level_reached,
        "durationSeconds": session.total_duration_seconds,
        "endReason": session.end_reason,
        "recommendation": recommendation,
        "technicalIndex": tolerance_index,
        "signals": {item["feature"]: item["value"] for item in basis},
        "clinicalStatus": "pending_professional_review",
        "evaluatedLevel": evaluated_level,
        "evaluatedAttempt": evaluated_attempt,
        "method": method,
        "methodVersion": method_version,
    }


def fingerprint(facts: dict, model: str, active: bool) -> str:
    payload = {"facts": facts, "model": model, "active": active, "promptVersion": PROMPT_VERSION}
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
                raise ValueError("Provider response is too large")
    data = json.loads(body)
    choice = data["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Provider response was incomplete")
    result = GeneratedText.model_validate_json(choice["message"]["content"])
    if result.recommendation != facts["recommendation"]:
        raise ValueError("Provider changed the recommendation")
    if re.search(r"[\d<>]|https?://|diagn[oó]stic|curad[oa]|mejor[ií]a cl[ií]nica|superad[oa].*fobia", result.summary, re.IGNORECASE):
        raise ValueError("Provider summary contains unsupported content")
    return result.summary.strip()
