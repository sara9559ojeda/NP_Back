"""Contrato interno del módulo de IA.

El módulo no conoce la base de datos ni la identidad de nadie: recibe rasgos anónimos de una
sesión (``SessionFeatures``) y devuelve un ``AnalysisResult``. Por eso puede separarse más
adelante como servicio sin tocar el resto (apartado 3.6.1 del documento).

Punto de extensión: la segunda versión (modelo supervisado interpretable con scikit-learn,
contrato sección 7) será otra clase que cumpla ``SessionAnalyzer`` y se registre en
``app.ai.registry``. Se entrenará solo con la exportación anónima, sin ``testSession``.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

Recommendation = Literal["advance", "repeat", "step_back"]
Effect = Literal["favorable", "unfavorable", "neutral"]


@dataclass(frozen=True)
class LevelFeatures:
    level: int
    attempt: int
    outcome: str
    criterion_met: bool
    permanence_seconds: float
    avoidance_count: int
    min_distance_m: float | None
    suds_before: int | None
    suds_after: int | None
    ended_at_epoch: float


@dataclass(frozen=True)
class SessionFeatures:
    phobia_grade: int | None
    level_reached: int | None
    end_reason: str | None
    levels: tuple[LevelFeatures, ...]


@dataclass(frozen=True)
class BasisItem:
    feature: str
    value: float | int | bool | None
    effect: Effect


@dataclass(frozen=True)
class AnalysisResult:
    method: str
    method_version: str
    tolerance_index: float
    recommendation: Recommendation
    basis: list[BasisItem] = field(default_factory=list)
    clinical_status: str = "pendiente_de_validar"


class SessionAnalyzer(Protocol):
    method: str
    method_version: str

    def analyze(self, features: SessionFeatures) -> AnalysisResult | None:
        """Devuelve ``None`` si no hay datos suficientes (por ejemplo, ningún registro de nivel)."""
        ...
