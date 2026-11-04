"""Línea base de reglas (contrato, sección 7). Pruebas unitarias, sin base de datos."""

import copy
import json

import pytest

from app.ai.features import session_features
from app.ai.rules_baseline import CONFIG_PATH, PENDING_STATUS, RulesBaselineAnalyzer, load_config
from tests.conftest import example


def _level(**changes) -> dict:
    payload = copy.deepcopy(example("record_level_record.request.json")["payload"])
    payload.update(changes)
    return payload


def _analyze(*levels: dict):
    features = session_features(phobia_grade=3, level_reached=2, end_reason="completed", level_payloads=levels)
    return RulesBaselineAnalyzer().analyze(features)


def test_every_parameter_is_marked_pending_validation():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["clinicalStatus"] == "pendiente_de_validar"
    for name, param in config["parameters"].items():
        assert param["status"] == PENDING_STATUS, name
        assert param["description"], name


def test_config_without_status_is_rejected(tmp_path):
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["parameters"]["advanceMinIndex"]["status"] = "validado"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_contract_example_gives_advance_with_explained_basis():
    result = _analyze(_level())
    assert result.recommendation == "advance"
    assert result.clinical_status == "pendiente_de_validar"
    assert result.method == "rules-baseline" and result.method_version == "0.1.0"
    # (1 + 0,6 + 0,6 + 1/3) / 4
    assert result.tolerance_index == pytest.approx(0.633, abs=1e-3)
    basis = {b.feature: (b.value, b.effect) for b in result.basis}
    assert basis["sudsDrop"] == (20, "favorable")
    assert basis["avoidanceCount"] == (2, "unfavorable")
    assert basis["criterionMet"] == (True, "favorable")


def test_criterion_not_met_never_advances():
    result = _analyze(_level(criterionMet=False, outcome="criterion_not_met", avoidanceCount=0))
    assert result.recommendation != "advance"


def test_safe_exit_never_advances_and_is_explained():
    result = _analyze(_level(outcome="safe_exit", avoidanceCount=0))
    assert result.recommendation != "advance"
    assert ("safeExit", True, "unfavorable") in {(b.feature, b.value, b.effect) for b in result.basis}


def test_low_index_steps_back_except_on_level_one():
    bad = {
        "criterionMet": False,
        "outcome": "abandoned",
        "avoidanceCount": 9,
        "suds": [{"phase": "before", "value": 30, "at": 0}, {"phase": "after", "value": 95, "at": 10}],
    }
    assert _analyze(_level(level=3, **bad)).recommendation == "step_back"
    assert _analyze(_level(level=1, **bad)).recommendation == "repeat"


def test_without_suds_weights_are_redistributed():
    result = _analyze(_level(suds=[], avoidanceCount=0))
    assert {b.feature for b in result.basis} == {"criterionMet", "avoidanceCount"}
    assert result.tolerance_index == 1.0


def test_evaluates_highest_level_last_attempt():
    first = _level(level=2, attempt=1, criterionMet=False, endedAt="2026-10-30T21:06:00Z", avoidanceCount=5)
    retry = _level(level=2, attempt=2, criterionMet=True, endedAt="2026-10-30T21:10:00Z", avoidanceCount=0)
    lower = _level(level=1, criterionMet=False)
    result = _analyze(lower, first, retry)
    assert {b.feature: b.value for b in result.basis}["avoidanceCount"] == 0


def test_no_levels_no_analysis():
    assert _analyze() is None
