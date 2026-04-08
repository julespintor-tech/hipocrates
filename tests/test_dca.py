"""
test_dca.py — Tests del DCA_Utility_Module.

Cubre:
  - NB calculado correctamente en theta de referencia
  - rango útil detectado cuando modelo domina
  - rango vacío cuando modelo nunca domina
  - decisión use_model / do_not_use / restrict
  - NB_treat_all correcto
  - precondiciones: tp/fp/prevalencia fuera de (0,1)
"""

import math
import pytest

from hipocrates.modules.dca import run_dca, net_benefit, net_benefit_treat_all, run
from hipocrates.utils.types import Action


# ── Correctitud aritmética ────────────────────────────────────────────────────

class TestNBCalculation:
    def test_nb_formula_exact(self):
        """
        NB(θ) = TP/N - FP/N * θ/(1-θ)
              = sens*prev - fpr*(1-prev)*θ/(1-θ)
        Con sens=0.8, fpr=0.2, prev=0.3, θ=0.2:
          = 0.8*0.3 - 0.2*0.7*(0.2/0.8)
          = 0.24 - 0.2*0.7*0.25
          = 0.24 - 0.035 = 0.205
        """
        nb = net_benefit(tp_rate=0.8, fp_rate=0.2, prevalence=0.3, theta=0.2)
        assert math.isclose(nb, 0.205, abs_tol=1e-9)

    def test_nb_treat_all_formula(self):
        """
        NB_all(θ) = prev - (1-prev)*θ/(1-θ)
        Con prev=0.3, θ=0.2:
          = 0.3 - 0.7*0.25 = 0.3 - 0.175 = 0.125
        """
        nb = net_benefit_treat_all(prevalence=0.3, theta=0.2)
        assert math.isclose(nb, 0.125, abs_tol=1e-9)

    def test_nb_at_reference_theta(self):
        out = run_dca(tp_rate=0.8, fp_rate=0.2, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        expected = net_benefit(0.8, 0.2, 0.3, 0.2)
        assert math.isclose(out.result["nb_at_theta"], expected, rel_tol=1e-6)

    def test_nb_treat_none_is_zero(self):
        out = run_dca(tp_rate=0.8, fp_rate=0.2, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        assert out.result["nb_treat_none"] == 0.0

    def test_nb_key_in_output(self):
        out = run_dca(tp_rate=0.82, fp_rate=0.18, prevalence=0.2, theta=0.15)
        assert out.NB is not None
        assert "theta" in out.NB
        assert "value" in out.NB
        assert math.isclose(out.NB["theta"], 0.15)


# ── Rango útil ────────────────────────────────────────────────────────────────

class TestUsefulRange:
    def test_good_model_has_positive_useful_range(self):
        """Un modelo bueno (alta sens, baja fpr) debe tener rango útil."""
        out = run_dca(tp_rate=0.9, fp_rate=0.1, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        assert out.result["n_useful_thetas"] > 0
        assert out.result["useful_theta_range"] is not None

    def test_terrible_model_has_no_useful_range(self):
        """Un modelo pésimo (sens muy baja) no debe dominar en ningún theta."""
        out = run_dca(tp_rate=0.05, fp_rate=0.95, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        assert out.result["n_useful_thetas"] == 0
        assert out.result["useful_theta_range"] is None

    def test_curve_has_correct_number_of_points(self):
        out = run_dca(tp_rate=0.8, fp_rate=0.2, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5], n_points=20)
        assert len(out.result["curve_model"]) == 20
        assert len(out.result["curve_treat_all"]) == 20


# ── Decisiones ────────────────────────────────────────────────────────────────

class TestDecisions:
    def test_good_model_use_model_or_restrict(self):
        out = run_dca(tp_rate=0.9, fp_rate=0.1, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        assert out.action in (Action.USE_MODEL, Action.RESTRICT_TO_THRESHOLD_RANGE)

    def test_bad_model_do_not_use(self):
        out = run_dca(tp_rate=0.05, fp_rate=0.95, prevalence=0.3,
                      theta=0.2, theta_range=[0.05, 0.5])
        assert out.action == Action.DO_NOT_USE_MODEL

    def test_model_dominates_flag(self):
        out = run_dca(tp_rate=0.82, fp_rate=0.18, prevalence=0.2,
                      theta=0.15)
        # Con estos parámetros el modelo debe dominar en θ=0.15
        assert out.result["model_dominates_at_reference_theta"] is True


# ── Precondiciones ────────────────────────────────────────────────────────────

class TestPreconditions:
    def test_tp_rate_zero_raises(self):
        with pytest.raises(ValueError):
            run_dca(tp_rate=0.0, fp_rate=0.2, prevalence=0.3, theta=0.2)

    def test_tp_rate_one_raises(self):
        with pytest.raises(ValueError):
            run_dca(tp_rate=1.0, fp_rate=0.2, prevalence=0.3, theta=0.2)

    def test_prevalence_zero_raises(self):
        with pytest.raises(ValueError):
            run_dca(tp_rate=0.8, fp_rate=0.2, prevalence=0.0, theta=0.2)

    def test_theta_zero_raises(self):
        with pytest.raises(ValueError):
            net_benefit(tp_rate=0.8, fp_rate=0.2, prevalence=0.3, theta=0.0)

    def test_theta_one_raises(self):
        with pytest.raises(ValueError):
            net_benefit(tp_rate=0.8, fp_rate=0.2, prevalence=0.3, theta=1.0)


# ── Interface estándar (run) ──────────────────────────────────────────────────

class TestRunInterface:
    def test_run_returns_clinical_output(self):
        payload = {
            "patient_id": "T",
            "module": "dca",
            "inputs": {
                "tp_rate": 0.82,
                "fp_rate": 0.18,
                "prevalence": 0.20,
                "theta": 0.15,
            },
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        }
        out = run(payload)
        assert out.NB is not None
        assert out.units_ok is True
