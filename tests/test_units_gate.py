"""
test_units_gate.py — Tests del Units_Validity_Gate.

Cubre:
  - probabilidad inválida (≤0, ≥1) bloquea
  - concentración negativa bloquea
  - NaN / inf bloquea
  - pH fuera de rango bloquea (abg_hh_stewart)
  - valores válidos permiten ejecución
"""

import math
import pytest

from hipocrates.core.units_gate import UnitsGateError, run_gate
from hipocrates.core.io_schema import validate_input


def _make_input(module: str, inputs: dict) -> object:
    payload = {
        "patient_id": "TEST",
        "module": module,
        "inputs": inputs,
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }
    return validate_input(payload)


# ── Bayes: probabilidades ─────────────────────────────────────────────────────

class TestProbabilityGate:
    def test_p0_zero_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": 0.0, "tests": []})
        with pytest.raises(UnitsGateError) as exc_info:
            run_gate(ci)
        assert any("p0" in v for v in exc_info.value.violations)

    def test_p0_one_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": 1.0, "tests": []})
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_p0_negative_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": -0.1, "tests": []})
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_p0_greater_than_one_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": 1.5, "tests": []})
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_valid_p0_passes(self):
        ci = _make_input("bayes_sprt", {"p0": 0.3, "tests": []})
        run_gate(ci)  # debe no lanzar


# ── Concentraciones negativas ─────────────────────────────────────────────────

class TestConcentrationGate:
    def test_negative_hco3_blocks(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 7.4, "paco2": 40.0, "hco3": -5.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError) as exc_info:
            run_gate(ci)
        assert any("hco3" in v for v in exc_info.value.violations)

    def test_negative_na_blocks(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 7.4, "paco2": 40.0, "hco3": 24.0,
            "na": -140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_valid_concentrations_pass(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 7.4, "paco2": 40.0, "hco3": 24.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        run_gate(ci)  # debe no lanzar


# ── NaN e inf ─────────────────────────────────────────────────────────────────

class TestNaNInfGate:
    def test_nan_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": float("nan"), "tests": []})
        with pytest.raises(UnitsGateError) as exc_info:
            run_gate(ci)
        assert any("p0" in v or "finito" in v for v in exc_info.value.violations)

    def test_inf_blocks(self):
        ci = _make_input("bayes_sprt", {"p0": float("inf"), "tests": []})
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_neg_inf_blocks(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 7.4, "paco2": float("-inf"), "hco3": 24.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)


# ── Rango específico (pH) ─────────────────────────────────────────────────────

class TestRangeRules:
    def test_ph_too_low_blocks(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 6.0,  # < 6.5
            "paco2": 40.0, "hco3": 24.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError) as exc_info:
            run_gate(ci)
        assert any("ph" in v for v in exc_info.value.violations)

    def test_ph_too_high_blocks(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 8.5,  # > 8.0
            "paco2": 40.0, "hco3": 24.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_valid_abg_passes(self):
        ci = _make_input("abg_hh_stewart", {
            "ph": 7.35, "paco2": 45.0, "hco3": 24.0,
            "na": 138.0, "k": 4.2, "cl": 104.0,
        })
        run_gate(ci)  # debe no lanzar

    def test_error_contains_all_violations(self):
        """El gate debe reportar TODAS las violaciones, no solo la primera."""
        ci = _make_input("abg_hh_stewart", {
            "ph": 5.0,       # rango inválido
            "paco2": 40.0,
            "hco3": -5.0,    # negativo
            "na": 140.0, "k": 4.0, "cl": 104.0,
        })
        with pytest.raises(UnitsGateError) as exc_info:
            run_gate(ci)
        assert len(exc_info.value.violations) >= 2
