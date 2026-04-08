"""
test_bayes_sprt.py — Tests del Bayes_SPRT_Engine.

Cubre:
  - posterior correcto en caso simple (sin tests)
  - actualización secuencial: posterior exacto con LR conocidos
  - umbral de tratamiento (start_treatment)
  - umbral de descarte (discard_diagnosis)
  - caso intermedio (obtain_test)
  - trazabilidad de pasos
  - precondiciones: p0 inválido, theta mal ordenado, LR ≤ 0
"""

import math
import pytest

from hipocrates.modules.bayes_sprt import run_bayes_sprt, run
from hipocrates.utils.types import Action


# ── Correctitud aritmética ────────────────────────────────────────────────────

class TestArithmetic:
    def test_no_tests_posterior_equals_prior(self):
        """Sin ningún test, posterior == prior."""
        out = run_bayes_sprt(p0=0.3, tests=[], theta_T=0.8, theta_A=0.1)
        assert math.isclose(out.p, 0.3, rel_tol=1e-9)

    def test_single_lr_3_from_025(self):
        """p0=0.25, LR=3 → odds 0.333*3=1 → p=0.5 exacto."""
        out = run_bayes_sprt(
            p0=0.25,
            tests=[{"name": "test_a", "lr": 3.0, "result": "pos"}],
            theta_T=0.8,
            theta_A=0.1,
        )
        assert math.isclose(out.p, 0.5, rel_tol=1e-9)

    def test_sequential_three_tests(self):
        """
        p0=0.25, LR=(3,2,4):
          O0 = 0.25/0.75 = 0.3333
          O3 = 0.3333 * 3 * 2 * 4 = 8.0
          p  = 8/9 = 0.8889
        """
        tests = [
            {"name": "a", "lr": 3.0, "result": "pos"},
            {"name": "b", "lr": 2.0, "result": "pos"},
            {"name": "c", "lr": 4.0, "result": "pos"},
        ]
        out = run_bayes_sprt(p0=0.25, tests=tests, theta_T=0.8, theta_A=0.1)
        assert math.isclose(out.p, 8.0 / 9.0, rel_tol=1e-9)

    def test_trace_length_matches_tests(self):
        tests = [{"name": f"t{i}", "lr": 1.5, "result": "pos"} for i in range(5)]
        out = run_bayes_sprt(p0=0.3, tests=tests, theta_T=0.9, theta_A=0.05)
        assert len(out.result["trace"]) == 5

    def test_lr_less_than_one_reduces_posterior(self):
        """LR < 1 debe reducir la probabilidad posterior."""
        out = run_bayes_sprt(
            p0=0.5,
            tests=[{"name": "neg", "lr": 0.1, "result": "neg"}],
            theta_T=0.8,
            theta_A=0.1,
        )
        assert out.p < 0.5


# ── Decisiones SPRT ───────────────────────────────────────────────────────────

class TestDecisions:
    def test_start_treatment_when_above_theta_T(self):
        """p0=0.25, LR secuencial lleva p > 0.8 → start_treatment."""
        tests = [
            {"name": "a", "lr": 3.0, "result": "pos"},
            {"name": "b", "lr": 2.0, "result": "pos"},
            {"name": "c", "lr": 4.0, "result": "pos"},
        ]
        out = run_bayes_sprt(p0=0.25, tests=tests, theta_T=0.8, theta_A=0.05)
        assert out.action == Action.START_TREATMENT

    def test_discard_diagnosis_when_below_theta_A(self):
        """LR muy bajo lleva p < 0.05 → discard_diagnosis."""
        tests = [{"name": "neg", "lr": 0.05, "result": "neg"}]
        out = run_bayes_sprt(p0=0.3, tests=tests, theta_T=0.8, theta_A=0.1)
        assert out.action == Action.DISCARD_DIAGNOSIS

    def test_obtain_test_in_intermediate_zone(self):
        """Sin tests y p0 en zona gris → obtain_test o observe."""
        # Un solo test que no resuelve la incertidumbre
        tests = [{"name": "med", "lr": 1.5, "result": "pos"}]
        out = run_bayes_sprt(p0=0.3, tests=tests, theta_T=0.9, theta_A=0.05)
        assert out.action in (Action.OBTAIN_TEST, Action.OBSERVE)

    def test_observe_when_no_tests_gray_zone(self):
        """Sin tests y p0 entre theta_A y theta_T → observe."""
        out = run_bayes_sprt(p0=0.5, tests=[], theta_T=0.8, theta_A=0.1)
        assert out.action == Action.OBSERVE


# ── Precondiciones ────────────────────────────────────────────────────────────

class TestPreconditions:
    def test_p0_zero_raises(self):
        with pytest.raises(ValueError, match="p0"):
            run_bayes_sprt(p0=0.0, tests=[], theta_T=0.8, theta_A=0.1)

    def test_p0_one_raises(self):
        with pytest.raises(ValueError, match="p0"):
            run_bayes_sprt(p0=1.0, tests=[], theta_T=0.8, theta_A=0.1)

    def test_thresholds_wrong_order_raises(self):
        with pytest.raises(ValueError):
            run_bayes_sprt(p0=0.3, tests=[], theta_T=0.1, theta_A=0.9)

    def test_lr_zero_raises(self):
        with pytest.raises(ValueError, match="LR"):
            run_bayes_sprt(
                p0=0.3,
                tests=[{"name": "bad", "lr": 0.0, "result": "pos"}],
                theta_T=0.8,
                theta_A=0.1,
            )

    def test_lr_negative_raises(self):
        with pytest.raises(ValueError, match="LR"):
            run_bayes_sprt(
                p0=0.3,
                tests=[{"name": "bad", "lr": -2.0, "result": "pos"}],
                theta_T=0.8,
                theta_A=0.1,
            )


# ── Interface estándar (run) ──────────────────────────────────────────────────

class TestRunInterface:
    def test_run_interface_returns_clinical_output(self):
        payload = {
            "patient_id": "X",
            "module": "bayes_sprt",
            "inputs": {
                "p0": 0.25,
                "tests": [{"name": "t", "lr": 3.0, "result": "pos"}],
                "theta_T": 0.8,
                "theta_A": 0.05,
            },
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        }
        out = run(payload)
        assert out.action in (Action.START_TREATMENT, Action.OBTAIN_TEST, Action.OBSERVE,
                               Action.DISCARD_DIAGNOSIS)
        assert out.units_ok is True
        assert 0.0 < out.p < 1.0
