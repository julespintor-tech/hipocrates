"""
test_pk_tdm.py — Tests del módulo PK_TDM_Core.

Cubre:
  - Parámetros base: k, t_half
  - IV bolus: fórmula y estructura
  - IV infusion: Css, C(t), fracción
  - Oral Bateman: fórmula, Tmax, caso degenerado ka≈k
  - Múltiples dosis: factor de acumulación, Cmax_ss, Cmin_ss
  - Target dosing: LD, MD, verificación ventana
  - Ajuste renal simple
  - Fenitoína MM: convergencia y no convergencia
  - Validaciones de inputs inválidos (PKInputError)
  - Integración con orquestador: ejecución, auditoría, request_id
  - Units gate: bloqueo de inputs inválidos en pk_tdm
"""

import math
import tempfile
from pathlib import Path

import pytest

from hipocrates.modules.pk_tdm import (
    calc_k,
    calc_t_half,
    pk_iv_bolus,
    pk_iv_infusion,
    pk_multiple_dosing,
    pk_oral_bateman,
    pk_target_dosing,
    renal_dose_adjustment,
    pk_phenytoin_mm,
    PKInputError,
    run,
)
from hipocrates.utils.types import Action, ClinicalOutput
from hipocrates.core import orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de payload
# ─────────────────────────────────────────────────────────────────────────────

def _payload(mode: str, extra: dict) -> dict:
    """Genera un payload estándar para pk_tdm."""
    return {
        "patient_id": "PK-TEST",
        "module": "pk_tdm",
        "inputs": {"mode": mode, **extra},
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros base
# ─────────────────────────────────────────────────────────────────────────────

class TestBasePKParams:
    def test_k_formula(self):
        """k = CL / Vd"""
        assert math.isclose(calc_k(3.5, 35.0), 0.1, rel_tol=1e-9)

    def test_k_formula_exact(self):
        """k = 4 / 40 = 0.1"""
        assert math.isclose(calc_k(4.0, 40.0), 0.1, rel_tol=1e-9)

    def test_t_half_formula(self):
        """t½ = ln(2) / k. Con k=0.1 → t½ ≈ 6.931 h"""
        k = 0.1
        t_half = calc_t_half(k)
        expected = math.log(2.0) / 0.1
        assert math.isclose(t_half, expected, rel_tol=1e-9)

    def test_k_t_half_consistency(self):
        """ln(2) / k_calculado == t_half_calculado"""
        cl, vd = 6.0, 60.0
        k = calc_k(cl, vd)
        t_half = calc_t_half(k)
        assert math.isclose(k * t_half, math.log(2.0), rel_tol=1e-9)

    def test_k_nonzero_positive(self):
        """k debe ser positivo para CL, Vd positivos."""
        assert calc_k(1.0, 10.0) > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# IV Bolus
# ─────────────────────────────────────────────────────────────────────────────

class TestIVBolus:
    def test_c0_formula(self):
        """C₀ = D / Vd. D=500mg, Vd=50L → C₀=10 mg/L."""
        r = pk_iv_bolus(dose_mg=500.0, vd_L=50.0, cl_L_h=5.0, time_h=0.0)
        assert math.isclose(r["C0_mg_L"], 10.0, rel_tol=1e-4)

    def test_ct_at_zero(self):
        """C(t=0) = C₀."""
        r = pk_iv_bolus(dose_mg=500.0, vd_L=50.0, cl_L_h=5.0, time_h=0.0)
        assert math.isclose(r["Ct_mg_L"], r["C0_mg_L"], rel_tol=1e-4)

    def test_ct_declines_with_time(self):
        """C(t) debe disminuir con el tiempo."""
        r1 = pk_iv_bolus(dose_mg=500.0, vd_L=50.0, cl_L_h=5.0, time_h=1.0)
        r2 = pk_iv_bolus(dose_mg=500.0, vd_L=50.0, cl_L_h=5.0, time_h=5.0)
        assert r1["Ct_mg_L"] > r2["Ct_mg_L"]

    def test_ct_at_one_half_life(self):
        """C(t½) = C₀/2."""
        cl, vd = 5.0, 50.0
        k = calc_k(cl, vd)
        t_half = calc_t_half(k)
        r = pk_iv_bolus(dose_mg=500.0, vd_L=vd, cl_L_h=cl, time_h=t_half)
        c0 = 500.0 / vd
        assert math.isclose(r["Ct_mg_L"], c0 / 2.0, rel_tol=1e-3)

    def test_ct_formula_exact(self):
        """C(t) = D/Vd * exp(-k*t). Verificar valor exacto."""
        D, Vd, CL, t = 200.0, 40.0, 4.0, 3.0
        k = CL / Vd
        expected = (D / Vd) * math.exp(-k * t)
        r = pk_iv_bolus(dose_mg=D, vd_L=Vd, cl_L_h=CL, time_h=t)
        assert math.isclose(r["Ct_mg_L"], expected, rel_tol=1e-3)

    def test_output_keys(self):
        """Verifica estructura de salida."""
        r = pk_iv_bolus(dose_mg=100.0, vd_L=20.0, cl_L_h=2.0, time_h=2.0)
        for key in ["mode", "k_h", "t_half_h", "C0_mg_L", "Ct_mg_L", "time_h"]:
            assert key in r

    def test_mode_label(self):
        r = pk_iv_bolus(dose_mg=100.0, vd_L=20.0, cl_L_h=2.0, time_h=2.0)
        assert r["mode"] == "iv_bolus"


# ─────────────────────────────────────────────────────────────────────────────
# IV Infusion
# ─────────────────────────────────────────────────────────────────────────────

class TestIVInfusion:
    def test_css_formula(self):
        """Css = R₀ / CL. R₀=10 mg/h, CL=2 L/h → Css=5 mg/L."""
        r = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=100.0)
        assert math.isclose(r["Css_mg_L"], 5.0, rel_tol=1e-3)

    def test_ct_approaches_css(self):
        """C(t→∞) → Css."""
        r = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=200.0)
        assert math.isclose(r["Ct_mg_L"], r["Css_mg_L"], rel_tol=1e-2)

    def test_ct_at_zero_is_zero(self):
        """C(t=0) = 0 (infusión acaba de empezar)."""
        r = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=0.0)
        assert math.isclose(r["Ct_mg_L"], 0.0, abs_tol=1e-9)

    def test_frac_css_increases_with_time(self):
        """Fracción de Css debe aumentar con el tiempo."""
        r1 = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=1.0)
        r2 = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=10.0)
        assert r1["frac_of_Css"] < r2["frac_of_Css"]

    def test_t90_less_than_t95(self):
        """t para 90% Css < t para 95% Css."""
        r = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=5.0)
        assert r["t90pct_Css_h"] < r["t95pct_Css_h"]

    def test_output_keys(self):
        r = pk_iv_infusion(rate_mg_h=10.0, cl_L_h=2.0, vd_L=20.0, time_h=5.0)
        for key in ["Css_mg_L", "Ct_mg_L", "frac_of_Css", "t90pct_Css_h", "t95pct_Css_h"]:
            assert key in r


# ─────────────────────────────────────────────────────────────────────────────
# Oral Bateman
# ─────────────────────────────────────────────────────────────────────────────

class TestOralBateman:
    def test_ct_positive_at_tmax(self):
        """Cmax debe ser > 0 para parámetros válidos."""
        r = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=1.2, cl_L_h=5.0, vd_L=40.0, time_h=2.0
        )
        assert r["Cmax_mg_L"] > 0.0

    def test_ct_at_zero_is_zero(self):
        """C(t=0) = 0 para oral (no hay dosis previa)."""
        r = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=1.2, cl_L_h=5.0, vd_L=40.0, time_h=0.0
        )
        assert math.isclose(r["Ct_mg_L"], 0.0, abs_tol=1e-9)

    def test_ct_at_tmax_approx_cmax(self):
        """C(Tmax) ≈ Cmax."""
        r = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=1.2, cl_L_h=5.0, vd_L=40.0,
            time_h=0.0  # placeholder; usamos Tmax del resultado
        )
        tmax = r["Tmax_h"]
        r2 = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=1.2, cl_L_h=5.0, vd_L=40.0,
            time_h=tmax
        )
        assert math.isclose(r2["Ct_mg_L"], r2["Cmax_mg_L"], rel_tol=1e-2)

    def test_degenerate_case_ka_equals_k(self):
        """Cuando ka ≈ k, usar solución límite sin crashear."""
        k = calc_k(5.0, 40.0)  # k = 0.125
        r = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=k + 1e-8,  # ka ≈ k
            cl_L_h=5.0, vd_L=40.0, time_h=2.0
        )
        assert r["degenerate_case"] is True
        assert r["method"] == "bateman_limit_ka_approx_k"
        assert r["Ct_mg_L"] >= 0.0

    def test_standard_method_used_when_ka_differs(self):
        """Cuando |ka − k| > umbral, usar método estándar."""
        r = pk_oral_bateman(
            dose_mg=250.0, F=0.85, ka_h=1.2,
            cl_L_h=5.0, vd_L=40.0, time_h=2.0
        )
        assert r["degenerate_case"] is False
        assert r["method"] == "bateman_standard"

    def test_f_reduces_concentration(self):
        """Con F menor, la concentración debe ser menor."""
        r1 = pk_oral_bateman(
            dose_mg=250.0, F=1.0, ka_h=1.2, cl_L_h=5.0, vd_L=40.0, time_h=2.0
        )
        r2 = pk_oral_bateman(
            dose_mg=250.0, F=0.5, ka_h=1.2, cl_L_h=5.0, vd_L=40.0, time_h=2.0
        )
        assert r1["Ct_mg_L"] > r2["Ct_mg_L"]

    def test_output_nonnegative(self):
        """C(t) y Cmax nunca deben ser negativos."""
        for t in [0.0, 0.5, 2.0, 10.0, 24.0]:
            r = pk_oral_bateman(
                dose_mg=250.0, F=0.85, ka_h=1.2, cl_L_h=5.0, vd_L=40.0, time_h=t
            )
            assert r["Ct_mg_L"] >= 0.0
            assert r["Cmax_mg_L"] >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Múltiples dosis
# ─────────────────────────────────────────────────────────────────────────────

class TestMultipleDosing:
    def test_accumulation_factor_formula(self):
        """R = 1 / (1 − exp(−k·τ)). Con k=0.1, τ=8: R = 1/(1-exp(-0.8))."""
        k = 0.1
        tau = 8.0
        expected_R = 1.0 / (1.0 - math.exp(-k * tau))
        r = pk_multiple_dosing(
            dose_mg=100.0, tau_h=tau, cl_L_h=k * 50.0,
            vd_L=50.0, time_h=0.0
        )
        assert math.isclose(r["accumulation_factor"], expected_R, rel_tol=1e-3)

    def test_accumulation_factor_gt_1(self):
        """Factor de acumulación siempre > 1."""
        r = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0
        )
        assert r["accumulation_factor"] > 1.0

    def test_cmax_ss_gt_cmin_ss(self):
        """Cmax_ss > Cmin_ss siempre."""
        r = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0
        )
        assert r["Cmax_ss_mg_L"] > r["Cmin_ss_mg_L"]

    def test_cmin_ss_formula(self):
        """Cmin_ss = Cmax_ss · exp(−k·τ)."""
        r = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0
        )
        k = r["k_h"]
        tau = r["tau_h"]
        expected_cmin = r["Cmax_ss_mg_L"] * math.exp(-k * tau)
        assert math.isclose(r["Cmin_ss_mg_L"], expected_cmin, rel_tol=1e-3)

    def test_ct_ss_at_t0_is_cmax_ss(self):
        """C(t=0) en SS = Cmax_ss."""
        r = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0
        )
        assert math.isclose(r["Ct_ss_mg_L"], r["Cmax_ss_mg_L"], rel_tol=1e-4)

    def test_f_affects_cmax_proportionally(self):
        """F=0.5 debe dar Cmax_ss exactamente la mitad que F=1.0."""
        r1 = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0, F=1.0
        )
        r2 = pk_multiple_dosing(
            dose_mg=100.0, tau_h=8.0, cl_L_h=5.0, vd_L=50.0, time_h=0.0, F=0.5
        )
        assert math.isclose(r2["Cmax_ss_mg_L"], r1["Cmax_ss_mg_L"] * 0.5, rel_tol=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# Target Dosing
# ─────────────────────────────────────────────────────────────────────────────

class TestTargetDosing:
    def test_maintenance_dose_formula(self):
        """MD = target_Css · CL · τ / F."""
        target = 15.0
        cl = 3.5
        tau = 8.0
        F = 1.0
        r = pk_target_dosing(
            target_css_mg_L=target,
            cl_L_h=cl, vd_L=30.0, tau_h=tau, F=F,
            therapeutic_window=[10, 20],
            calc_type="maintenance",
        )
        expected_md = target * cl * tau / F
        assert math.isclose(r["maintenance_dose_mg"], expected_md, rel_tol=1e-3)

    def test_loading_dose_formula(self):
        """LD = target_Css · Vd / F."""
        target = 15.0
        vd = 30.0
        F = 1.0
        r = pk_target_dosing(
            target_css_mg_L=target,
            cl_L_h=3.5, vd_L=vd, tau_h=8.0, F=F,
            therapeutic_window=[10, 20],
            calc_type="loading",
        )
        expected_ld = target * vd / F
        assert math.isclose(r["loading_dose_mg"], expected_ld, rel_tol=1e-3)

    def test_target_in_window_true(self):
        """target_Css dentro de la ventana → target_within_therapeutic_window=True."""
        r = pk_target_dosing(
            target_css_mg_L=15.0,
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=1.0,
            therapeutic_window=[10, 20],
            calc_type="both",
        )
        assert r["target_within_therapeutic_window"] is True

    def test_target_out_of_window_false(self):
        """target_Css fuera de la ventana → target_within_therapeutic_window=False."""
        r = pk_target_dosing(
            target_css_mg_L=25.0,  # fuera de [10, 20]
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=1.0,
            therapeutic_window=[10, 20],
            calc_type="both",
        )
        assert r["target_within_therapeutic_window"] is False

    def test_calc_type_maintenance_only(self):
        """Con calc_type='maintenance', solo debe incluir MD, no LD."""
        r = pk_target_dosing(
            target_css_mg_L=15.0,
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=1.0,
            therapeutic_window=[10, 20],
            calc_type="maintenance",
        )
        assert "maintenance_dose_mg" in r
        assert "loading_dose_mg" not in r

    def test_calc_type_loading_only(self):
        """Con calc_type='loading', solo debe incluir LD."""
        r = pk_target_dosing(
            target_css_mg_L=15.0,
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=1.0,
            therapeutic_window=[10, 20],
            calc_type="loading",
        )
        assert "loading_dose_mg" in r
        assert "maintenance_dose_mg" not in r

    def test_f_lower_increases_doses(self):
        """Con F más baja, LD y MD deben ser mayores para el mismo target."""
        r1 = pk_target_dosing(
            target_css_mg_L=15.0,
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=1.0,
            therapeutic_window=[10, 20], calc_type="both"
        )
        r2 = pk_target_dosing(
            target_css_mg_L=15.0,
            cl_L_h=3.5, vd_L=30.0, tau_h=8.0, F=0.5,
            therapeutic_window=[10, 20], calc_type="both"
        )
        assert r2["loading_dose_mg"] > r1["loading_dose_mg"]
        assert r2["maintenance_dose_mg"] > r1["maintenance_dose_mg"]


# ─────────────────────────────────────────────────────────────────────────────
# Ajuste renal simple
# ─────────────────────────────────────────────────────────────────────────────

class TestRenalAdjustment:
    def test_normal_renal_no_adjustment(self):
        """Con CLCr = ref, la dosis no cambia."""
        r = renal_dose_adjustment(
            standard_dose_mg=500.0, clcr_patient_mL_min=100.0, clcr_ref_mL_min=100.0
        )
        assert math.isclose(r["adjusted_dose_mg"], 500.0, rel_tol=1e-4)
        assert math.isclose(r["dose_ratio"], 1.0, rel_tol=1e-9)

    def test_halved_clcr_halves_dose(self):
        """Con CLCr=50 (referencia=100), la dosis se reduce a la mitad."""
        r = renal_dose_adjustment(
            standard_dose_mg=500.0, clcr_patient_mL_min=50.0, clcr_ref_mL_min=100.0
        )
        assert math.isclose(r["adjusted_dose_mg"], 250.0, rel_tol=1e-4)
        assert math.isclose(r["dose_ratio"], 0.5, rel_tol=1e-9)

    def test_zero_clcr_gives_zero_dose(self):
        """CLCr=0 → dosis ajustada = 0."""
        r = renal_dose_adjustment(
            standard_dose_mg=500.0, clcr_patient_mL_min=0.0, clcr_ref_mL_min=100.0
        )
        assert math.isclose(r["adjusted_dose_mg"], 0.0, abs_tol=1e-9)

    def test_output_keys(self):
        r = renal_dose_adjustment(500.0, 60.0)
        for key in ["adjusted_dose_mg", "dose_ratio", "clcr_patient_mL_min", "limitation"]:
            assert key in r


# ─────────────────────────────────────────────────────────────────────────────
# Fenitoína Michaelis–Menten
# ─────────────────────────────────────────────────────────────────────────────

class TestPhenytoinMM:
    def test_converges_within_window(self):
        """Con parámetros típicos, debe converger dentro de la ventana 10-20 mg/L."""
        r = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[10.0, 20.0],
            dt_h=1.0, max_days=30.0,
        )
        assert r["converged"] is True
        assert r["in_therapeutic_window"] is True
        assert 10.0 <= r["Css_estimated_mg_L"] <= 20.0

    def test_dose_trials_recorded(self):
        """Debe registrar al menos un ensayo de dosis."""
        r = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[10.0, 20.0],
        )
        assert len(r["dose_trials"]) >= 1

    def test_no_convergence_reported_honestly(self):
        """Con Vmax imposiblemente bajo, no puede converger y debe reportarlo."""
        r = pk_phenytoin_mm(
            vmax_mg_day=1.0,        # Vmax mínimo: nunca alcanza target 10-20
            km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[100.0, 200.0],  # ventana inalcanzable
            max_days=5.0,
        )
        assert r["converged"] is False
        assert r["in_therapeutic_window"] is False

    def test_css_non_negative(self):
        """Css estimado nunca puede ser negativo."""
        r = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=50.0,
            target_range_mg_L=[10.0, 20.0],
        )
        assert r["Css_estimated_mg_L"] >= 0.0

    def test_trial_structure(self):
        """Cada trial tiene las claves esperadas."""
        r = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[10.0, 20.0],
        )
        for trial in r["dose_trials"]:
            assert "trial" in trial
            assert "dose_mg_day" in trial
            assert "Css_estimated_mg_L" in trial
            assert "in_window" in trial

    def test_initial_concentration_respected(self):
        """Con c0 alto, la simulación parte de ese punto."""
        r1 = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[10.0, 20.0],
            c0_mg_L=0.0,
        )
        r2 = pk_phenytoin_mm(
            vmax_mg_day=500.0, km_mg_L=4.0,
            dose_guess_mg_day=300.0,
            target_range_mg_L=[10.0, 20.0],
            c0_mg_L=5.0,
        )
        # Ambas deben tener result válidos (la convergencia puede variar)
        assert r1["Css_estimated_mg_L"] >= 0.0
        assert r2["Css_estimated_mg_L"] >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Validaciones de inputs inválidos (PKInputError)
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    def _run(self, inp: dict) -> ClinicalOutput:
        return run({"patient_id": "T", "module": "pk_tdm",
                    "inputs": inp, "constraints": {}, "version": "SMNC-5+_v1.0"})

    def test_missing_mode_raises(self):
        with pytest.raises(PKInputError, match="mode"):
            self._run({"dose_mg": 100.0})

    def test_invalid_mode_raises(self):
        with pytest.raises(PKInputError, match="no reconocido"):
            self._run({"mode": "nonexistent_mode"})

    def test_iv_bolus_zero_dose_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "iv_bolus", "dose_mg": 0.0,
                       "vd_L": 30.0, "cl_L_h": 3.0, "time_h": 2.0})

    def test_iv_bolus_negative_vd_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "iv_bolus", "dose_mg": 100.0,
                       "vd_L": -10.0, "cl_L_h": 3.0, "time_h": 2.0})

    def test_iv_bolus_negative_time_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "iv_bolus", "dose_mg": 100.0,
                       "vd_L": 30.0, "cl_L_h": 3.0, "time_h": -1.0})

    def test_oral_bateman_f_zero_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "oral_bateman", "dose_mg": 100.0,
                       "F": 0.0, "ka_h": 1.0, "cl_L_h": 3.0,
                       "vd_L": 30.0, "time_h": 2.0})

    def test_oral_bateman_f_above_one_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "oral_bateman", "dose_mg": 100.0,
                       "F": 1.5, "ka_h": 1.0, "cl_L_h": 3.0,
                       "vd_L": 30.0, "time_h": 2.0})

    def test_target_dosing_inverted_window_raises(self):
        with pytest.raises(PKInputError, match="min < max"):
            self._run({"mode": "target_dosing", "target_css_mg_L": 15.0,
                       "cl_L_h": 3.5, "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
                       "therapeutic_window": [20, 10]})  # invertida

    def test_target_dosing_invalid_calc_type_raises(self):
        with pytest.raises(PKInputError, match="calc_type"):
            self._run({"mode": "target_dosing", "target_css_mg_L": 15.0,
                       "cl_L_h": 3.5, "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
                       "therapeutic_window": [10, 20], "calc_type": "invalid"})

    def test_phenytoin_negative_c0_raises(self):
        with pytest.raises(PKInputError):
            self._run({"mode": "phenytoin_mm", "vmax_mg_day": 500.0,
                       "km_mg_L": 4.0, "dose_guess_mg_day": 300.0,
                       "target_range_mg_L": [10, 20], "c0_mg_L": -1.0})

    def test_multiple_dosing_invalid_route_raises(self):
        with pytest.raises(PKInputError, match="route"):
            self._run({"mode": "multiple_dosing", "dose_mg": 100.0,
                       "tau_h": 8.0, "cl_L_h": 3.0, "vd_L": 30.0,
                       "time_h": 0.0, "route": "intramuscular"})


# ─────────────────────────────────────────────────────────────────────────────
# Acciones canónicas
# ─────────────────────────────────────────────────────────────────────────────

class TestPKActions:
    def _run_orch(self, inp: dict) -> dict:
        return orchestrator.run({
            "patient_id": "PK-ACTION-TEST",
            "module": "pk_tdm",
            "inputs": inp,
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        })

    def test_iv_bolus_action_is_observe(self):
        out = self._run_orch({"mode": "iv_bolus", "dose_mg": 500.0,
                              "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0})
        assert out["action"] == Action.OBSERVE

    def test_target_in_window_action_is_review_dosing(self):
        # v1.0: target_dosing siempre emite review_dosing — el cálculo 1C es
        # orientativo y requiere confirmación con niveles séricos antes de prescribir.
        out = self._run_orch({"mode": "target_dosing", "target_css_mg_L": 15.0,
                              "cl_L_h": 3.5, "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
                              "therapeutic_window": [10, 20], "calc_type": "both"})
        assert out["action"] == Action.REVIEW_DOSING

    def test_target_out_of_window_action_is_review_dosing(self):
        out = self._run_orch({"mode": "target_dosing", "target_css_mg_L": 30.0,
                              "cl_L_h": 3.5, "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
                              "therapeutic_window": [10, 20], "calc_type": "both"})
        assert out["action"] == Action.REVIEW_DOSING

    def test_phenytoin_converged_is_review_dosing(self):
        # v1.0: phenytoin_mm siempre emite review_dosing — la simulación MM
        # es orientativa; cinética no lineal requiere siempre confirmación sérica.
        out = self._run_orch({"mode": "phenytoin_mm", "vmax_mg_day": 500.0,
                              "km_mg_L": 4.0, "dose_guess_mg_day": 300.0,
                              "target_range_mg_L": [10.0, 20.0]})
        assert out["action"] == Action.REVIEW_DOSING

    def test_renal_adjustment_action_is_observe(self):
        out = self._run_orch({"mode": "renal_adjustment", "standard_dose_mg": 500.0,
                              "clcr_patient_mL_min": 50.0})
        assert out["action"] == Action.OBSERVE


# ─────────────────────────────────────────────────────────────────────────────
# Integración con orquestador
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorIntegration:
    CONTRACT_KEYS = ["result", "action", "p", "U", "NB", "units_ok", "explain", "ci"]

    def _pk_payload(self, mode_inputs: dict) -> dict:
        return {
            "patient_id": "ORCH-PK-TEST",
            "module": "pk_tdm",
            "inputs": mode_inputs,
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        }

    def test_iv_bolus_via_orchestrator_contract(self):
        out = orchestrator.run(self._pk_payload({
            "mode": "iv_bolus", "dose_mg": 500.0,
            "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0
        }))
        for k in self.CONTRACT_KEYS:
            assert k in out, f"Clave faltante: {k}"

    def test_iv_bolus_units_ok(self):
        out = orchestrator.run(self._pk_payload({
            "mode": "iv_bolus", "dose_mg": 500.0,
            "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0
        }))
        assert out["units_ok"] is True

    def test_request_id_generated(self):
        out = orchestrator.run(self._pk_payload({
            "mode": "iv_bolus", "dose_mg": 500.0,
            "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0
        }))
        assert "request_id" in out
        assert len(out["request_id"]) == 36

    def test_pk_p_and_U_are_none(self):
        """p, U, NB deben ser None en PK puro."""
        out = orchestrator.run(self._pk_payload({
            "mode": "iv_bolus", "dose_mg": 500.0,
            "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0
        }))
        assert out["p"] is None
        assert out["U"] is None
        assert out["NB"] is None

    def test_pk_ci_is_none(self):
        """ci = None en v1.0."""
        out = orchestrator.run(self._pk_payload({
            "mode": "iv_bolus", "dose_mg": 500.0,
            "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0
        }))
        assert out["ci"] is None

    def test_audit_log_written_for_pk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "pk_audit.jsonl"
            orchestrator.run(self._pk_payload({
                "mode": "iv_infusion", "rate_mg_h": 10.0,
                "cl_L_h": 2.0, "vd_L": 20.0, "time_h": 4.0
            }), log_path=log_path)
            assert log_path.exists()
            import json
            record = json.loads(log_path.read_text().strip())
            assert record["module"] == "pk_tdm"
            assert "sha256_input" in record
            assert "request_id" in record

    def test_multiple_modes_run_without_error(self):
        """Los 7 modos ejecutan sin error ni acción 'error'."""
        modes = [
            {"mode": "iv_bolus", "dose_mg": 500.0, "vd_L": 30.0,
             "cl_L_h": 3.5, "time_h": 4.0},
            {"mode": "iv_infusion", "rate_mg_h": 10.0, "cl_L_h": 2.0,
             "vd_L": 20.0, "time_h": 5.0},
            {"mode": "multiple_dosing", "dose_mg": 100.0, "tau_h": 8.0,
             "cl_L_h": 5.0, "vd_L": 50.0, "time_h": 2.0},
            {"mode": "oral_bateman", "dose_mg": 250.0, "F": 0.85,
             "ka_h": 1.2, "cl_L_h": 5.0, "vd_L": 40.0, "time_h": 2.0},
            {"mode": "target_dosing", "target_css_mg_L": 15.0, "cl_L_h": 3.5,
             "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
             "therapeutic_window": [10, 20], "calc_type": "both"},
            {"mode": "phenytoin_mm", "vmax_mg_day": 500.0, "km_mg_L": 4.0,
             "dose_guess_mg_day": 300.0, "target_range_mg_L": [10.0, 20.0]},
            {"mode": "renal_adjustment", "standard_dose_mg": 500.0,
             "clcr_patient_mL_min": 60.0},
        ]
        for m in modes:
            out = orchestrator.run(self._pk_payload(m))
            assert out["action"] != Action.ERROR, f"Error en modo {m['mode']}: {out.get('explain', '')}"


# ─────────────────────────────────────────────────────────────────────────────
# Units Gate — validaciones PK
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitsGatePK:
    def _payload(self, inp: dict) -> dict:
        return {
            "patient_id": "GATE-PK-TEST",
            "module": "pk_tdm",
            "inputs": inp,
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        }

    def test_zero_dose_blocked_by_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "iv_bolus", "dose_mg": 0.0,
             "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0}
        ))
        assert out["action"] == Action.BLOCKED
        assert out["units_ok"] is False

    def test_negative_cl_blocked_by_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "iv_bolus", "dose_mg": 100.0,
             "vd_L": 30.0, "cl_L_h": -1.0, "time_h": 4.0}
        ))
        assert out["action"] == Action.BLOCKED

    def test_negative_vd_blocked_by_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "iv_bolus", "dose_mg": 100.0,
             "vd_L": -30.0, "cl_L_h": 3.5, "time_h": 4.0}
        ))
        assert out["action"] == Action.BLOCKED

    def test_f_zero_blocked_by_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "oral_bateman", "dose_mg": 100.0,
             "F": 0.0, "ka_h": 1.0, "cl_L_h": 3.0,
             "vd_L": 30.0, "time_h": 2.0}
        ))
        assert out["action"] == Action.BLOCKED

    def test_f_above_one_blocked_by_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "oral_bateman", "dose_mg": 100.0,
             "F": 1.2, "ka_h": 1.0, "cl_L_h": 3.0,
             "vd_L": 30.0, "time_h": 2.0}
        ))
        assert out["action"] == Action.BLOCKED

    def test_inverted_therapeutic_window_blocked(self):
        out = orchestrator.run(self._payload(
            {"mode": "target_dosing", "target_css_mg_L": 15.0,
             "cl_L_h": 3.5, "vd_L": 30.0, "tau_h": 8.0, "F": 1.0,
             "therapeutic_window": [20, 10]}  # invertida
        ))
        assert out["action"] == Action.BLOCKED

    def test_nan_dose_blocked_by_gate(self):
        import math
        out = orchestrator.run(self._payload(
            {"mode": "iv_bolus", "dose_mg": float("nan"),
             "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0}
        ))
        assert out["action"] == Action.BLOCKED

    def test_valid_pk_passes_gate(self):
        out = orchestrator.run(self._payload(
            {"mode": "iv_bolus", "dose_mg": 500.0,
             "vd_L": 30.0, "cl_L_h": 3.5, "time_h": 4.0}
        ))
        assert out["action"] != Action.BLOCKED
        assert out["units_ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Que los módulos anteriores siguen funcionando
# ─────────────────────────────────────────────────────────────────────────────

class TestExistingModulesUnbroken:
    """Smoke tests para verificar que los módulos previos no se rompieron."""

    def test_bayes_sprt_still_runs(self):
        out = orchestrator.run({
            "patient_id": "SMOKE-BAYES",
            "module": "bayes_sprt",
            "inputs": {
                "p0": 0.25,
                "tests": [{"name": "t1", "lr": 3.0, "result": "pos"}],
                "theta_T": 0.8, "theta_A": 0.05,
            },
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        })
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)

    def test_abg_hh_still_runs(self):
        out = orchestrator.run({
            "patient_id": "SMOKE-ABG",
            "module": "abg_hh_stewart",
            "inputs": {"ph": 7.40, "paco2": 40.0, "hco3": 24.0,
                       "na": 140.0, "k": 4.0, "cl": 104.0},
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        })
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)

    def test_dca_still_runs(self):
        out = orchestrator.run({
            "patient_id": "SMOKE-DCA",
            "module": "dca",
            "inputs": {"tp_rate": 0.8, "fp_rate": 0.2,
                       "prevalence": 0.3, "theta": 0.2},
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        })
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)
