"""Selección del método de análisis (``NP_AI_METHOD``)."""

from functools import lru_cache

from app.ai.base import SessionAnalyzer
from app.ai.rules_baseline import RulesBaselineAnalyzer

# Para añadir el modelo supervisado: crear una clase que cumpla SessionAnalyzer y registrarla aquí.
_ANALYZERS: dict[str, type] = {
    "rules-baseline": RulesBaselineAnalyzer,
}


@lru_cache
def get_analyzer(method: str) -> SessionAnalyzer:
    try:
        return _ANALYZERS[method]()
    except KeyError as exc:
        raise ValueError(f"Método de análisis desconocido: {method}") from exc
