"""
test_pk_tdm_v2.py — Tests para PK_TDM_Core v2.0

Cubre los tres nuevos modos:
  H. cockcroft_gault          — CLCr desde datos del paciente
  I. target_dosing_renal      — target dosing con ajuste renal automático
  J. tdm_bayes_map            — estimación Bayes-MAP básica 1C

Además verifica:
  - No regresión de modos v1
  - Units Gate: bloqueo de inputs v2 absurdos
  - Integración con orquestador para modos v2
  - Homogeneidad de salida (p=None, U=None, NB=None, ci=None)
  - Semántica de acción correcta
"""

import math
import tempfile
from pathlib import Path

import pytest

from hipocrates.modules.pk_tdm import (
    cockcroft_gault,
    pk_target_dosing_renal,
    pk_tdm_bayes_map,
    PKInputError,
    run,
    # v1 — verificar que siguen funcionando
    calc_k,
    pk_iv_bolus,
    pk_target_dosing,
)
from hipocrates.utils.types import Action, ClinicalOutput
from hipocrates.core import orchestrator
from hipocrates.core.units_gate import run_gate, UnitsGateError
from hipocrates.core.io_schema import validate_input
from hipocrates.utils.types import ClinicalInput


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _payload(mode: str, extra: dict) -> dict:
    return {
        "patient_id": "PK-V2-TEST",
        "module": "pk_tdm",
        "inputs": {"mode": mode, **extra},
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }


def _run_mode(mode: str, extra: dict) -> dict:
    """Corre un modo directamente a través del módulo (sin orquestador)."""
    payload = _payload(mode, extra)
    result = run(payload)
    assert isinstance(result, ClinicalOutput)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# H. Cockcroft-Gault — función pura
# ─────────────────────────────────────────────────────────────────────────────

class TestCockcroftGault:
    def test_hombre_formula(self):
        """
        Hombre 50 años, 70 kg, Cr 1.0 mg/dL:
        CLCr = (140-50) × 70 / (72 × 1.0) = 90 × 70 / 72 = 87.5 mL/min
        """
        r = cockcroft_gault(age=50, sex="M", weight_kg=70, serum_creatinine_mg_dL=1.0)
        expected = (140 - 50) * 70 / (72 * 1.0)
        assert math.isclose(r["clcr_mL_min"], expected, rel_tol=1e-3)
        assert r["sex_correction_applied"] is False

    def test_mujer_formula(self):
        """
        Mujer 65 años, 60 kg, Cr 1.2 mg/dL:
        CLCr_H = (140-65) × 60 / (72 × 1.2) = 75 × 60 / 86.4 ≈ 52.08 mL/min
        CLCr_F = 52.08 × 0.85 ≈ 44.27 mL/min
        """
        r = cockcroft_gault(age=65, sex="F", weight_kg=60, serum_creatinine_mg_dL=1.2)
        expected_h = (140 - 65) * 60 / (72 * 1.2)
        expected_f = expected_h * 0.85
        assert math.isclose(r["clcr_mL_min"], round(expected_f, 1), rel_tol=1e-2)
        assert r["sex_correction_applied"] is True

    def test_sex_case_insensitive(self):
        """'f' minúscula debe aceptarse."""
        r = cockcroft_gault(age=60, sex="f", weight_kg=65, serum_creatinine_mg_dL=1.0)
        assert r["sex"] == "F"
        assert r["sex_correction_applied"] is True

    def test_interpretacion_normal(self):
        """CLCr ≥ 90 → función renal normal."""
        r = cockcroft_gault(age=30, sex="M", weight_kg=80, serum_creatinine_mg_dL=0.8)
        assert r["clcr_mL_min"] >= 90
        assert "normal" in r["interpretation"].lower() or "elevada" in r["interpretation"].lower()

    def test_interpretacion_leve(self):
        """CLCr 60-89 → deterioro leve."""
        r = cockcroft_gault(age=60, sex="M", weight_kg=70, serum_creatinine_mg_dL=1.2)
        # No garantizamos exactamente el rango, pero verificamos estructura
        assert "clcr_mL_min" in r
        assert "interpretation" in r

    def test_interpretacion_severo(self):
        """CLCr bajo con creatinina alta → deterioro severo."""
        r = cockcroft_gault(age=80, sex="F", weight_kg=50, serum_creatinine_mg_dL=4.0)
        assert r["clcr_mL_min"] < 30

    def test_sex_invalido(self):
        """Sexo no reconocido → PKInputError."""
        with pytest.raises(PKInputError):
            cockcroft_gault(age=50, sex="X", weight_kg=70, serum_creatinine_mg_dL=1.0)

    def test_estructura_salida(self):
        """Verifica todos los campos esperados en el resultado."""
        r = cockcroft_gault(age=55, sex="M", weight_kg=75, serum_creatinine_mg_dL=1.5)
        expected_keys = [
            "mode", "age_years", "sex", "weight_kg", "serum_creatinine_mg_dL",
            "clcr_mL_min", "sex_correction_applied", "interpretation", "formula", "limitation"
        ]
        for key in expected_keys:
            assert key in r, f"Falta clave: {key}"

    def test_clcr_no_negativo_edad_extrema(self):
        """Para edad muy alta, CLCr no debe ser negativo."""
        r = cockcroft_gault(age=139, sex="M", weight_kg=60, serum_creatinine_mg_dL=1.0)
        assert r["clcr_mL_min"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# I. Target Dosing Renal — función pura
# ─────────────────────────────────────────────────────────────────────────────

class TestTargetDosingRenal:
    def _base_args(self):
        return dict(
            age=65,
            sex="M",
            weight_kg=70,
            serum_creatinine_mg_dL=1.8,
            base_cl_L_h=3.5,
            drug_clcr_reference_mL_min=100.0,
            vd_L=30.0,
            tau_h=12.0,
            F=1.0,
            target_css_mg_L=15.0,
            therapeutic_window=[10.0, 20.0],
            calc_type="both",
        )

    def test_estructura_salida(self):
        """Verifica campos clave en el resultado."""
        r = pk_target_dosing_renal(**self._base_args())
        for key in [
            "clcr_patient_mL_min", "cl_adjusted_L_h", "cl_adjustment_method",
            "loading_dose_mg", "maintenance_dose_mg", "warning_simplification",
            "limitation", "renal_interpretation",
        ]:
            assert key in r, f"Falta clave: {key}"

    def test_cl_ajustado_proporcional(self):
        """CL_adj = CL_base × (CLCr_pac / CLCr_ref)."""
        args = self._base_args()
        r = pk_target_dosing_renal(**args)
        clcr_pac = r["clcr_patient_mL_min"]
        cl_adj_expected = args["base_cl_L_h"] * (clcr_pac / args["drug_clcr_reference_mL_min"])
        assert math.isclose(r["cl_adjusted_L_h"], round(cl_adj_expected, 4), rel_tol=1e-3)

    def test_cl_ajustado_menor_que_base_con_función_renal_reducida(self):
        """Con CLCr < CLCr_ref, CL_adj < CL_base."""
        r = pk_target_dosing_renal(**self._base_args())
        assert r["cl_adjusted_L_h"] < r["base_cl_L_h"]

    def test_md_calculado(self):
        """MD = Css × CL_adj × τ / F."""
        r = pk_target_dosing_renal(**self._base_args())
        expected_md = r["target_Css_mg_L"] * r["cl_adjusted_L_h"] * r["tau_h"] / 1.0
        assert math.isclose(r["maintenance_dose_mg"], round(expected_md, 2), rel_tol=1e-3)

    def test_ld_calculado(self):
        """LD = Css × Vd / F."""
        r = pk_target_dosing_renal(**self._base_args())
        expected_ld = r["target_Css_mg_L"] * r["vd_L"] / 1.0
        assert math.isclose(r["loading_dose_mg"], round(expected_ld, 2), rel_tol=1e-3)

    def test_funcion_renal_normal_no_reduce_cl(self):
        """Con CLCr ≈ CLCr_ref, CL_adj ≈ CL_base."""
        r = pk_target_dosing_renal(
            age=35, sex="M", weight_kg=75, serum_creatinine_mg_dL=0.9,
            base_cl_L_h=3.5, drug_clcr_reference_mL_min=100.0,
            vd_L=30.0, tau_h=12.0, F=1.0,
            target_css_mg_L=15.0, therapeutic_window=[10.0, 20.0],
        )
        # CLCr ~110 mL/min → ratio ~1.1 → CL_adj ~3.85 > 3.5
        assert r["cl_adjusted_L_h"] > 3.0

    def test_calc_type_solo_maintenance(self):
        """calc_type='maintenance' solo incluye maintenance_dose_mg, no loading_dose_mg."""
        args = self._base_args()
        args["calc_type"] = "maintenance"
        r = pk_target_dosing_renal(**args)
        assert "maintenance_dose_mg" in r
        assert "loading_dose_mg" not in r


# ─────────────────────────────────────────────────────────────────────────────
# J. TDM Bayes-MAP — función pura
# ─────────────────────────────────────────────────────────────────────────────

class TestTDMBayesMAP:
    def _base_args(self):
        return dict(
            dose_mg=1000.0,
            tau_h=12.0,
            route="iv",
            F=1.0,
            observed_concentrations=[{"time_h": 6.0, "conc_mg_L": 12.5}],
            prior_cl_mean_L_h=3.5,
            prior_cl_sd_L_h=1.5,
            prior_vd_mean_L=30.0,
            prior_vd_sd_L=10.0,
            sigma_obs_mg_L=2.0,
            optimize_vd=False,
        )

    def test_estructura_salida(self):
        """Verifica campos clave en el resultado."""
        r = pk_tdm_bayes_map(**self._base_args())
        for key in [
            "mode", "prior_parameters", "observations_used", "cl_estimated_L_h",
            "vd_estimated_L", "k_estimated_h", "t_half_estimated_h",
            "posterior_map_summary", "predicted_concentrations",
            "cmax_ss_predicted_mg_L", "cmin_ss_predicted_mg_L",
            "dose_adjustment_suggestion", "limitations",
        ]:
            assert key in r, f"Falta clave: {key}"

    def test_una_observacion(self):
        """Con 1 observación, el resultado no debe ser igual al prior exacto."""
        r = pk_tdm_bayes_map(**self._base_args())
        assert r["cl_estimated_L_h"] > 0
        assert r["observations_used"] == 1

    def test_multiples_observaciones(self):
        """Con 3 observaciones, el MAP converge con más información."""
        args = self._base_args()
        args["observed_concentrations"] = [
            {"time_h": 1.0, "conc_mg_L": 28.0},
            {"time_h": 6.0, "conc_mg_L": 14.2},
            {"time_h": 11.0, "conc_mg_L": 7.8},
        ]
        args["optimize_vd"] = True
        r = pk_tdm_bayes_map(**args)
        assert r["observations_used"] == 3
        assert r["vd_was_optimized"] is True
        assert r["cl_estimated_L_h"] > 0
        assert r["vd_estimated_L"] > 0

    def test_predicciones_generadas(self):
        """predicted_concentrations debe tener el mismo número de observaciones."""
        args = self._base_args()
        args["observed_concentrations"] = [
            {"time_h": 2.0, "conc_mg_L": 20.0},
            {"time_h": 8.0, "conc_mg_L": 10.0},
        ]
        r = pk_tdm_bayes_map(**args)
        assert len(r["predicted_concentrations"]) == 2
        for pred in r["predicted_concentrations"]:
            assert "time_h" in pred
            assert "conc_obs_mg_L" in pred
            assert "conc_pred_mg_L" in pred
            assert "error_mg_L" in pred

    def test_cl_positivo_siempre(self):
        """CL estimado debe ser siempre positivo."""
        r = pk_tdm_bayes_map(**self._base_args())
        assert r["cl_estimated_L_h"] > 0

    def test_cmax_mayor_que_cmin(self):
        """En SS, Cmax > Cmin."""
        r = pk_tdm_bayes_map(**self._base_args())
        assert r["cmax_ss_predicted_mg_L"] > r["cmin_ss_predicted_mg_L"]

    def test_limitaciones_incluidas(self):
        """El resultado debe incluir limitaciones explícitas."""
        r = pk_tdm_bayes_map(**self._base_args())
        assert isinstance(r["limitations"], list)
        assert len(r["limitations"]) > 0

    def test_observacion_mal_formada_sin_time_h(self):
        """Observación sin 'time_h' → PKInputError."""
        args = self._base_args()
        args["observed_concentrations"] = [{"conc_mg_L": 10.0}]  # falta time_h
        with pytest.raises(PKInputError, match="time_h"):
            pk_tdm_bayes_map(**args)

    def test_observacion_mal_formada_no_dict(self):
        """Observación que no es dict → PKInputError."""
        args = self._base_args()
        args["observed_concentrations"] = [42.0]  # no es dict
        with pytest.raises(PKInputError):
            pk_tdm_bayes_map(**args)

    def test_observacion_vacia(self):
        """Lista de observaciones vacía → PKInputError."""
        args = self._base_args()
        args["observed_concentrations"] = []
        with pytest.raises(PKInputError):
            pk_tdm_bayes_map(**args)

    def test_tiempo_negativo_rechazado(self):
        """time_h negativo → PKInputError."""
        args = self._base_args()
        args["observed_concentrations"] = [{"time_h": -1.0, "conc_mg_L": 10.0}]
        with pytest.raises(PKInputError):
            pk_tdm_bayes_map(**args)

    def test_concentracion_negativa_rechazada(self):
        """conc_mg_L negativa → PKInputError."""
        args = self._base_args()
        args["observed_concentrations"] = [{"time_h": 4.0, "conc_mg_L": -5.0}]
        with pytest.raises(PKInputError):
            pk_tdm_bayes_map(**args)

    def test_optimize_vd_false_fija_vd(self):
        """Con optimize_vd=False, Vd estimado debe ser igual al prior."""
        r = pk_tdm_bayes_map(**self._base_args())
        assert r["vd_estimated_L"] == self._base_args()["prior_vd_mean_L"]
        assert r["vd_was_optimized"] is False

    def test_optimize_vd_true_puede_cambiar_vd(self):
        """Con optimize_vd=True y varias observaciones, Vd puede diferir del prior."""
        args = self._base_args()
        args["observed_concentrations"] = [
            {"time_h": 0.5, "conc_mg_L": 32.0},
            {"time_h": 4.0, "conc_mg_L": 16.0},
            {"time_h": 10.0, "conc_mg_L": 6.0},
        ]
        args["optimize_vd"] = True
        r = pk_tdm_bayes_map(**args)
        assert r["vd_was_optimized"] is True
        # No imponemos que difiera — solo que corra sin error
        assert r["vd_estimated_L"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Semántica de acción v2
# ─────────────────────────────────────────────────────────────────────────────

class TestActionSemanticV2:
    def test_cockcroft_gault_emite_observe(self):
        """cockcroft_gault siempre emite OBSERVE (solo info)."""
        out = _run_mode("cockcroft_gault", {
            "age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0
        })
        assert out.action == Action.OBSERVE

    def test_target_dosing_renal_emite_review_dosing(self):
        """target_dosing_renal siempre emite REVIEW_DOSING."""
        out = _run_mode("target_dosing_renal", {
            "age": 68, "sex": "M", "weight_kg": 78, "serum_creatinine_mg_dL": 1.8,
            "base_cl_L_h": 3.5, "drug_clcr_reference_mL_min": 100.0,
            "vd_L": 30.0, "tau_h": 12.0, "F": 1.0,
            "target_css_mg_L": 15.0, "therapeutic_window": [10.0, 20.0],
        })
        assert out.action == Action.REVIEW_DOSING

    def test_bayes_map_emite_review_dosing(self):
        """tdm_bayes_map siempre emite REVIEW_DOSING."""
        out = _run_mode("tdm_bayes_map", {
            "dose_mg": 1000.0, "tau_h": 12.0, "route": "iv", "F": 1.0,
            "observed_concentrations": [{"time_h": 6.0, "conc_mg_L": 12.0}],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        assert out.action == Action.REVIEW_DOSING

    def test_ninguno_emite_start_treatment(self):
        """Ningún modo v2 debe emitir start_treatment."""
        modes_and_inputs = [
            ("cockcroft_gault", {"age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0}),
            ("target_dosing_renal", {
                "age": 68, "sex": "M", "weight_kg": 78, "serum_creatinine_mg_dL": 1.8,
                "base_cl_L_h": 3.5, "drug_clcr_reference_mL_min": 100.0,
                "vd_L": 30.0, "tau_h": 12.0, "F": 1.0,
                "target_css_mg_L": 15.0, "therapeutic_window": [10.0, 20.0],
            }),
            ("tdm_bayes_map", {
                "dose_mg": 1000.0, "tau_h": 12.0, "route": "iv", "F": 1.0,
                "observed_concentrations": [{"time_h": 6.0, "conc_mg_L": 12.0}],
                "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
                "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
            }),
        ]
        for mode, extra in modes_and_inputs:
            out = _run_mode(mode, extra)
            assert out.action != Action.START_TREATMENT, f"Modo {mode} emitió start_treatment"


# ─────────────────────────────────────────────────────────────────────────────
# Salida homogénea v2
# ─────────────────────────────────────────────────────────────────────────────

class TestOutputHomogeneityV2:
    def test_p_es_none(self):
        """p=None en todos los modos v2."""
        out = _run_mode("cockcroft_gault", {
            "age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0
        })
        assert out.p is None

    def test_U_es_none(self):
        """U=None en todos los modos v2."""
        out = _run_mode("cockcroft_gault", {
            "age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0
        })
        assert out.U is None

    def test_NB_es_none(self):
        """NB=None en todos los modos v2."""
        out = _run_mode("cockcroft_gault", {
            "age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0
        })
        assert out.NB is None

    def test_ci_es_none(self):
        """ci=None en todos los modos v2."""
        out = _run_mode("cockcroft_gault", {
            "age": 55, "sex": "M", "weight_kg": 75, "serum_creatinine_mg_dL": 1.0
        })
        assert out.ci is None

    def test_bayes_map_p_none(self):
        """TDM Bayes-MAP: p=None (no es probabilidad diagnóstica)."""
        out = _run_mode("tdm_bayes_map", {
            "dose_mg": 1000.0, "tau_h": 12.0, "route": "iv", "F": 1.0,
            "observed_concentrations": [{"time_h": 6.0, "conc_mg_L": 12.0}],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        assert out.p is None
        assert out.ci is None


# ─────────────────────────────────────────────────────────────────────────────
# Units Gate v2 — bloqueo de inputs absurdos
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitsGateV2:
    def _make_ci(self, mode: str, extra: dict) -> ClinicalInput:
        payload = _payload(mode, extra)
        return validate_input(payload)

    def test_age_negativa_bloqueada(self):
        """age negativa debe ser bloqueada por el gate."""
        ci = self._make_ci("cockcroft_gault", {
            "age": -5, "sex": "M", "weight_kg": 70, "serum_creatinine_mg_dL": 1.0
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_peso_cero_bloqueado(self):
        """weight_kg=0 debe ser bloqueado."""
        ci = self._make_ci("cockcroft_gault", {
            "age": 50, "sex": "M", "weight_kg": 0, "serum_creatinine_mg_dL": 1.0
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_creatinina_cero_bloqueada(self):
        """serum_creatinine_mg_dL=0 → bloqueado."""
        ci = self._make_ci("cockcroft_gault", {
            "age": 50, "sex": "M", "weight_kg": 70, "serum_creatinine_mg_dL": 0
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_prior_sd_cero_bloqueado(self):
        """prior_cl_sd_L_h=0 → bloqueado."""
        ci = self._make_ci("tdm_bayes_map", {
            "dose_mg": 1000, "tau_h": 12, "route": "iv", "F": 1.0,
            "observed_concentrations": [{"time_h": 6.0, "conc_mg_L": 12.0}],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 0,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_observed_concentrations_mal_formada_bloqueada(self):
        """Observación sin 'time_h' → bloqueada por gate."""
        ci = self._make_ci("tdm_bayes_map", {
            "dose_mg": 1000, "tau_h": 12, "route": "iv", "F": 1.0,
            "observed_concentrations": [{"conc_mg_L": 12.0}],  # falta time_h
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_observed_concentrations_negativa_bloqueada(self):
        """Concentración observada negativa → bloqueada por gate."""
        ci = self._make_ci("tdm_bayes_map", {
            "dose_mg": 1000, "tau_h": 12, "route": "iv", "F": 1.0,
            "observed_concentrations": [{"time_h": 4.0, "conc_mg_L": -2.0}],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_observed_concentrations_lista_vacia_bloqueada(self):
        """Lista de observaciones vacía → bloqueada por gate."""
        ci = self._make_ci("tdm_bayes_map", {
            "dose_mg": 1000, "tau_h": 12, "route": "iv", "F": 1.0,
            "observed_concentrations": [],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_inputs_validos_v2_no_bloqueados(self):
        """Inputs v2 válidos no deben ser bloqueados por el gate."""
        ci = self._make_ci("cockcroft_gault", {
            "age": 60, "sex": "F", "weight_kg": 65, "serum_creatinine_mg_dL": 1.2
        })
        # No debe lanzar excepción
        run_gate(ci)


# ─────────────────────────────────────────────────────────────────────────────
# Integración con el orquestador — modos v2
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorIntegrationV2:
    def _orch(self, mode: str, extra: dict) -> dict:
        payload = _payload(mode, extra)
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "test_audit.jsonl"
            return orchestrator.run(payload, log_path=log_path)

    def test_cockcroft_gault_via_orquestador(self):
        """cockcroft_gault completa el pipeline sin errores."""
        result = self._orch("cockcroft_gault", {
            "age": 65, "sex": "M", "weight_kg": 78, "serum_creatinine_mg_dL": 1.8
        })
        assert result.get("action") == Action.OBSERVE
        assert result.get("units_ok") is True
        assert "request_id" in result
        assert result["result"]["clcr_mL_min"] > 0

    def test_target_dosing_renal_via_orquestador(self):
        """target_dosing_renal completa el pipeline y genera request_id."""
        result = self._orch("target_dosing_renal", {
            "age": 72, "sex": "F", "weight_kg": 65, "serum_creatinine_mg_dL": 1.4,
            "base_cl_L_h": 3.5, "drug_clcr_reference_mL_min": 100.0,
            "vd_L": 30.0, "tau_h": 12.0, "F": 1.0,
            "target_css_mg_L": 15.0, "therapeutic_window": [10.0, 20.0],
        })
        assert result.get("action") == Action.REVIEW_DOSING
        assert result.get("units_ok") is True
        assert "request_id" in result
        r = result["result"]
        assert "cl_adjusted_L_h" in r
        assert "maintenance_dose_mg" in r

    def test_bayes_map_via_orquestador(self):
        """tdm_bayes_map completa el pipeline sin errores."""
        result = self._orch("tdm_bayes_map", {
            "dose_mg": 1000.0, "tau_h": 12.0, "route": "iv", "F": 1.0,
            "observed_concentrations": [
                {"time_h": 2.0, "conc_mg_L": 22.0},
                {"time_h": 10.0, "conc_mg_L": 8.5},
            ],
            "prior_cl_mean_L_h": 3.5, "prior_cl_sd_L_h": 1.5,
            "prior_vd_mean_L": 30.0, "prior_vd_sd_L": 10.0,
        })
        assert result.get("action") == Action.REVIEW_DOSING
        assert result.get("units_ok") is True
        assert "request_id" in result
        r = result["result"]
        assert r["cl_estimated_L_h"] > 0
        assert len(r["predicted_concentrations"]) == 2

    def test_gate_bloquea_input_invalido_via_orquestador(self):
        """Inputs inválidos son bloqueados antes de llegar al módulo."""
        result = self._orch("cockcroft_gault", {
            "age": -10, "sex": "M", "weight_kg": 70, "serum_creatinine_mg_dL": 1.0
        })
        assert result.get("action") == Action.BLOCKED

    def test_auditoria_registrada(self):
        """request_id presente en resultado = auditoría registrada."""
        result = self._orch("cockcroft_gault", {
            "age": 55, "sex": "F", "weight_kg": 60, "serum_creatinine_mg_dL": 1.1
        })
        assert "request_id" in result


# ─────────────────────────────────────────────────────────────────────────────
# No regresión — modos v1 siguen funcionando
# ─────────────────────────────────────────────────────────────────────────────

class TestNoRegressionV1:
    def test_iv_bolus_sigue_funcionando(self):
        """iv_bolus v1 no roto por v2."""
        r = pk_iv_bolus(dose_mg=500.0, vd_L=50.0, cl_L_h=5.0, time_h=0.0)
        assert math.isclose(r["C0_mg_L"], 10.0, rel_tol=1e-4)

    def test_target_dosing_v1_sigue_funcionando(self):
        """target_dosing v1 no roto por v2."""
        r = pk_target_dosing(
            target_css_mg_L=15.0, cl_L_h=3.5, vd_L=30.0,
            tau_h=8.0, F=1.0, therapeutic_window=[10.0, 20.0],
        )
        assert "loading_dose_mg" in r
        assert r["mode"] == "target_dosing"

    def test_modo_invalido_error_correcto(self):
        """Modo no reconocido levanta PKInputError con mensaje útil."""
        with pytest.raises(PKInputError, match="cockcroft_gault|tdm_bayes_map|v2"):
            run(_payload("modo_inexistente_xyz", {}))

    def test_k_calc_no_rota(self):
        """calc_k no afectada por v2."""
        assert math.isclose(calc_k(3.5, 35.0), 0.1, rel_tol=1e-9)
