import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.ai.groq_summary import request_summary


@pytest.mark.parametrize("content,finish", [
    ({"summary": "Has mejorado un 80 por ciento.", "recommendation": "repeat"}, "stop"),
    ({"summary": "Una explicación con <b>contenido</b> no permitido.", "recommendation": "repeat"}, "stop"),
    ({"summary": "La recomendación técnica indica repetir el nivel evaluado.", "recommendation": "advance"}, "stop"),
    ({"summary": "La recomendación técnica indica repetir el nivel evaluado.", "recommendation": "repeat"}, "length"),
])
def test_invalid_or_incomplete_generated_text_is_rejected(content, finish):
    settings = SimpleNamespace(groq_model="openai/gpt-oss-20b", groq_api_key=SecretStr("test-key"))
    def respond(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {"content": json.dumps(content)}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(ValueError):
        request_summary({"recommendation": "repeat"}, settings, client)
