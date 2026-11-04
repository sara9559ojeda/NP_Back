"""Línea base de reglas (contrato, sección 7; apartado 3.6.3 del documento).

Todos los parámetros están en ``rules_baseline_config.json`` y están marcados como
«provisional técnico, sin fuente, pendiente de validar». Este archivo solo aplica la lógica.
"""

import json
from pathlib import Path
from typing import Any

from app.ai.base import AnalysisResult, BasisItem, Effect, LevelFeatures, Recommendation, SessionFeatures

CONFIG_PATH = Path(__file__).with_name("rules_baseline_config.json")
PENDING_STATUS = "provisional técnico, sin fuente, pendiente de validar"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    for name, param in config["parameters"].items():
        if param.get("status") != PENDING_STATUS:
            raise ValueError(f"El parámetro {name} no declara su estado de validación")
    return config


def evaluated_level(levels: tuple[LevelFeatures, ...]) -> LevelFeatures | None:
    """El nivel más alto registrado en la sesión y, dentro de él, el último intento terminado."""
    if not levels:
        return None
    return max(levels, key=lambda lv: (lv.level, lv.ended_at_epoch, lv.attempt))


class RulesBaselineAnalyzer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_config()
        self.method = self.config["method"]
        self.method_version = self.config["methodVersion"]
        self.clinical_status = self.config["clinicalStatus"]
        self._p = {name: param["value"] for name, param in self.config["parameters"].items()}

    def _effect(self, score: float) -> Effect:
        neutral = float(self._p["neutralScore"])
        if score > neutral:
            return "favorable"
        if score < neutral:
            return "unfavorable"
        return "neutral"

    def analyze(self, features: SessionFeatures) -> AnalysisResult | None:
        target = evaluated_level(features.levels)
        if target is None:
            return None

        scale_min, scale_max = (float(v) for v in self._p["sudsScaleRange"])
        span = scale_max - scale_min
        scores: dict[str, float] = {}
        values: dict[str, float | int | bool] = {}

        scores["criterionMet"] = 1.0 if target.criterion_met else 0.0
        values["criterionMet"] = target.criterion_met

        if target.suds_before is not None and target.suds_after is not None:
            drop = target.suds_before - target.suds_after
            scores["sudsDrop"] = (drop + span) / (2 * span)
            values["sudsDrop"] = drop
        if target.suds_after is not None:
            scores["sudsAfter"] = 1.0 - (target.suds_after - scale_min) / span
            values["sudsAfter"] = target.suds_after

        scores["avoidanceCount"] = 1.0 / (1.0 + target.avoidance_count)
        values["avoidanceCount"] = target.avoidance_count

        weights: dict[str, float] = self._p["weights"]
        total_weight = sum(weights[name] for name in scores)
        index = sum(scores[name] * weights[name] for name in scores) / total_weight
        index = round(min(1.0, max(0.0, index)), 3)

        basis = [BasisItem(name, values[name], self._effect(scores[name])) for name in scores]

        safe_exit = target.outcome == "safe_exit"
        if safe_exit:
            basis.append(BasisItem("safeExit", True, "unfavorable"))

        recommendation: Recommendation
        can_advance = (target.criterion_met or not self._p["requireCriterionMetToAdvance"]) and not (
            safe_exit and self._p["safeExitBlocksAdvance"]
        )
        if index >= float(self._p["advanceMinIndex"]) and can_advance:
            recommendation = "advance"
        elif index < float(self._p["stepBackMaxIndex"]) and target.level > 1:
            recommendation = "step_back"
        else:
            recommendation = "repeat"

        return AnalysisResult(
            method=self.method,
            method_version=self.method_version,
            tolerance_index=index,
            recommendation=recommendation,
            basis=basis,
            clinical_status=self.clinical_status,
        )
