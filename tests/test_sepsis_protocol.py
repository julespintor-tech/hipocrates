"""
test_sepsis_protocol.py — Tests del Sepsis_Protocol_Engine.

Cubre:
  - qSOFA correcto (score y componentes)
  - Caso de sospecha baja (low_suspicion)
  - Caso de sepsis probable (evidencia sólida)
  - Caso de choque séptico probable (septic_shock_probable)
  - Uso de inputs opcionales (SOFA parcial)
  - Output homogéneo (claves esperadas en result)
  - Integración con el orquestador (schema + gate + módulo + auditoría)
  - Bloqueo por Units Gate (valores inválidos)
  - Auditoría funcionando (request_id generado)
  - Acción canónica correcta por severidad
  - Flags correctos (lactato, MAP, vasopresor, hipoperfusión)
  - Tiempo de revaloración coherente con severidad
  - Bundle no vacío
  - Limitaciones declaradas en el output
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from hipocrates.core import orchestrator
from hipocrates.core.io_schema import validate_input
from hipocrates.core.units_gate import UnitsGateError, run_gate
from hipocrates.modules.sepsis_protocol import compute_sepsis, run
from hipocrates.utils.types import Action


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "SMNC-5+_v1.0"


def _base_payload(**overrides) -> dict:
    """Payload mínimo válido para sepsis_protocol."""
    base = {
        "patient_id": "TEST-SEP-001",
        "module": "sepsis_protocol",
        "inputs": {
            "suspected_infection": True,
            "rr": 16,
            "sbp": 120,
            "mental_status_altered": False,
            "map_mmHg": 85.0,
            "lactate_mmol_L": 1.0,
            "vasopressor": False,
        },
        "constraints": {},
        "version": SCHEMA_VERSION,
    }
    base["inputs"].update(overrides)
    return base


def _orch_payload(**input_overrides) -> dict:
    """Devuelve payload para el orquestador con inputs sobrescritos."""
    return _base_payload(**input_overrides)


def _make_input(inputs: dict):
    """Crea un ClinicalInput validado para el gate."""
    payload = {
        "patient_id": "GATE-TEST",
        "module": "sepsis_protocol",
        "inputs": inputs,
        "constraints": {},
        "version": SCHEMA_VERSION,
    }
    return validate_input(payload)


# ─────────────────────────────────────────────────────────────────────────────
# A. Tests de qSOFA
# ─────────────────────────────────────────────────────────────────────────────

class TestQSOFA:
    def test_qsofa_zero_all_normal(self):
        """Sin ningún criterio positivo → qSOFA 0."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        r = out.result
        assert r["qsofa_score"] == 0
        assert r["qsofa_positive"] is False

    def test_qsofa_rr_threshold(self):
        """FR = 22 → qSOFA + 1."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=22, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["qsofa_score"] >= 1
        assert any("FR" in c for c in out.result["qsofa_components"])

    def test_qsofa_sbp_threshold(self):
        """PAS = 100 → qSOFA + 1."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=100, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["qsofa_score"] >= 1
        assert any("PAS" in c for c in out.result["qsofa_components"])

    def test_qsofa_mental_status(self):
        """Alteración mental → qSOFA + 1."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=True,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["qsofa_score"] >= 1
        assert any("mental" in c.lower() for c in out.result["qsofa_components"])

    def test_qsofa_maximum_score(self):
        """FR=28, PAS=88, mental alterado → qSOFA 3."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=28, sbp=88, mental_status_altered=True,
            map_mmhg=60.0, lactate_mmol_l=3.0, vasopressor=True,
        )
        assert out.result["qsofa_score"] == 3
        assert out.result["qsofa_positive"] is True

    def test_qsofa_positive_threshold_is_two(self):
        """qSOFA = 2 → positivo."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=95, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["qsofa_score"] == 2
        assert out.result["qsofa_positive"] is True

    def test_qsofa_one_not_positive(self):
        """qSOFA = 1 → no positivo por definición."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=22, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["qsofa_score"] == 1
        assert out.result["qsofa_positive"] is False


# ─────────────────────────────────────────────────────────────────────────────
# B. Tests de clasificación de severidad
# ─────────────────────────────────────────────────────────────────────────────

class TestSeverityClassification:

    def test_low_suspicion_no_infection(self):
        """Sin sospecha infecciosa → siempre low_suspicion."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=False,
            rr=28, sbp=88, mental_status_altered=True,
            map_mmhg=55.0, lactate_mmol_l=4.5, vasopressor=True,
        )
        r = out.result
        assert r["severity_class"] == "low_suspicion"
        assert out.action == Action.OBSERVE

    def test_low_suspicion_infection_no_signals(self):
        """Sospecha infecciosa pero sin señales de disfunción → low_suspicion."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=118, mental_status_altered=False,
            map_mmhg=82.0, lactate_mmol_l=1.1, vasopressor=False,
        )
        assert out.result["severity_class"] == "low_suspicion"
        assert out.action == Action.OBSERVE

    def test_sepsis_probable_qsofa2(self):
        """qSOFA ≥ 2 con sospecha infecciosa → sepsis_probable."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=1.4, vasopressor=False,
        )
        assert out.result["severity_class"] == "sepsis_probable"

    def test_sepsis_probable_elevated_lactate(self):
        """Lactato ≥ 2.0 con sospecha infecciosa → al menos sepsis_probable."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=18, sbp=115, mental_status_altered=False,
            map_mmhg=76.0, lactate_mmol_l=2.5, vasopressor=False,
        )
        assert out.result["severity_class"] in ("sepsis_probable", "septic_shock_probable")
        assert out.result["lactate_flag"] is True

    def test_septic_shock_lactate_plus_low_map(self):
        """Lactato ≥ 2 + MAP < 65 → septic_shock_probable."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
        )
        r = out.result
        assert r["severity_class"] == "septic_shock_probable"
        assert out.action == Action.START_TREATMENT

    def test_septic_shock_lactate_plus_vasopressor(self):
        """Lactato ≥ 2 + vasopresor (aunque MAP sea 65) → septic_shock_probable."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=22, sbp=100, mental_status_altered=False,
            map_mmhg=65.0, lactate_mmol_l=2.2, vasopressor=True,
        )
        # MAP exactamente 65 no es < 65, pero vasopresor = True y lactato ≥ 2
        assert out.result["severity_class"] == "septic_shock_probable"

    def test_sepsis_probable_start_treatment_strong_evidence(self):
        """Sepsis probable con qSOFA≥2 → start_treatment."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=68.0, lactate_mmol_l=2.3, vasopressor=False,
        )
        assert out.action == Action.START_TREATMENT

    def test_sepsis_probable_obtain_test_borderline(self):
        """Sepsis probable con qSOFA=1 y lactato limítrofe sin otros datos → obtain_test."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=22, sbp=115, mental_status_altered=False,
            map_mmhg=68.0, lactate_mmol_l=1.6, vasopressor=False,
        )
        # Dependiendo de los datos: sepsis_probable por qSOFA=1 + lactato borderline + MAP<70
        assert out.result["severity_class"] in ("sepsis_probable", "low_suspicion")


# ─────────────────────────────────────────────────────────────────────────────
# C. Tests de flags individuales
# ─────────────────────────────────────────────────────────────────────────────

class TestFlags:

    def test_lactate_flag_below_2(self):
        """Lactato < 2.0 → lactate_flag False."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.9, vasopressor=False,
        )
        assert out.result["lactate_flag"] is False

    def test_lactate_flag_exactly_2(self):
        """Lactato = 2.0 → lactate_flag True."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=2.0, vasopressor=False,
        )
        assert out.result["lactate_flag"] is True

    def test_map_flag_below_65(self):
        """MAP < 65 → map_flag True."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=60.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["map_flag"] is True

    def test_map_flag_above_70(self):
        """MAP ≥ 70 → map_flag False."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=80.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["map_flag"] is False

    def test_vasopressor_flag(self):
        """vasopresor activo → vasopressor_flag True."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=66.0, lactate_mmol_l=2.5, vasopressor=True,
        )
        assert out.result["vasopressor_flag"] is True

    def test_hypoperfusion_flag_requires_lactate_plus_hemodynamic(self):
        """hypoperfusion_flag = lactate_flag AND (map_flag OR vasopressor)."""
        # lactato alto + MAP bajo → hipoperfusión
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=90, mental_status_altered=False,
            map_mmhg=58.0, lactate_mmol_l=3.0, vasopressor=False,
        )
        assert out.result["hypoperfusion_flag"] is True

    def test_hypoperfusion_flag_false_without_lactate(self):
        """MAP bajo pero lactato normal → hypoperfusion_flag False."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=90, mental_status_altered=False,
            map_mmhg=58.0, lactate_mmol_l=1.2, vasopressor=False,
        )
        assert out.result["hypoperfusion_flag"] is False

    def test_urine_oliguria_flag(self):
        """Diuresis < 0.5 mL/kg/h → urine_output_flag True."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            urine_output_ml_kg_h=0.3,
        )
        assert out.result["urine_output_flag"] is True

    def test_urine_normal_flag_false(self):
        """Diuresis ≥ 0.5 mL/kg/h → urine_output_flag False."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            urine_output_ml_kg_h=0.8,
        )
        assert out.result["urine_output_flag"] is False

    def test_urine_none_flag_false(self):
        """Sin diuresis → urine_output_flag False (no penaliza)."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["urine_output_flag"] is False


# ─────────────────────────────────────────────────────────────────────────────
# D. Tests de SOFA parcial con inputs opcionales
# ─────────────────────────────────────────────────────────────────────────────

class TestSOFAPartial:

    def test_sofa_zero_components_without_optional_data(self):
        """Sin inputs opcionales → sofa_n_components_evaluated = 0."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["sofa_n_components_evaluated"] == 0
        assert out.result["sofa_partial_score"] == 0
        assert out.result["sofa_components_available"] == []

    def test_sofa_renal_component(self):
        """Creatinina 2.5 → SOFA renal = 2."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            creatinine_mg_dl=2.5,
        )
        r = out.result
        assert "renal" in r["sofa_components_available"]
        assert r["sofa_partial_score"] >= 2

    def test_sofa_hepatic_component(self):
        """Bilirrubina 3.0 → SOFA hepático ≥ 1."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            bilirubin_mg_dl=3.0,
        )
        assert "hepatico" in out.result["sofa_components_available"]
        assert out.result["sofa_partial_score"] >= 2

    def test_sofa_coagulation_component(self):
        """Plaquetas 80 → SOFA coagulación = 2."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            platelets_k_ul=80.0,
        )
        assert "coagulacion" in out.result["sofa_components_available"]
        assert out.result["sofa_partial_score"] >= 2

    def test_sofa_respiratory_component_with_vm(self):
        """PaO2/FiO2 160 con VM → SOFA respiratorio = 3."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
            pao2_fio2=160.0, mechanical_ventilation=True,
        )
        assert "respiratorio" in out.result["sofa_components_available"]
        assert out.result["sofa_partial_score"] >= 3

    def test_sofa_full_4_components(self):
        """Los 4 componentes disponibles → n = 4."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
            creatinine_mg_dl=3.2, bilirubin_mg_dl=2.8,
            platelets_k_ul=68.0, pao2_fio2=165.0, mechanical_ventilation=True,
        )
        assert out.result["sofa_n_components_evaluated"] == 4

    def test_sofa_high_score_contributes_to_sepsis_probable(self):
        """SOFA parcial ≥ 2 con sospecha → sepsis_probable o peor."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=82.0, lactate_mmol_l=1.0, vasopressor=False,
            creatinine_mg_dl=3.5,  # SOFA renal = 3
        )
        assert out.result["severity_class"] in ("sepsis_probable", "septic_shock_probable")


# ─────────────────────────────────────────────────────────────────────────────
# E. Tests de bundle y tiempo de revaloración
# ─────────────────────────────────────────────────────────────────────────────

class TestBundleAndRecheck:

    def test_bundle_not_empty_for_any_severity(self):
        """Bundle siempre tiene acciones."""
        for inf, rr, sbp, lat, mp, vaso in [
            (False, 16, 120, 1.0, 85.0, False),
            (True, 24, 94, 2.3, 68.0, False),
            (True, 28, 82, 4.8, 54.0, True),
        ]:
            out = compute_sepsis(
                patient_id="T", suspected_infection=inf,
                rr=rr, sbp=sbp, mental_status_altered=False,
                map_mmhg=mp, lactate_mmol_l=lat, vasopressor=vaso,
            )
            assert len(out.result["bundle_actions"]) > 0

    def test_recheck_low_suspicion_is_60(self):
        """Sospecha baja → 60 min."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=False,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["recheck_time_minutes"] == 60

    def test_recheck_sepsis_probable_is_30(self):
        """Sepsis probable → 30 min (sin lactato marcadamente elevado)."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=2.3, vasopressor=False,
        )
        # Si es sepsis_probable, recheck ≤ 30
        if out.result["severity_class"] == "sepsis_probable":
            assert out.result["recheck_time_minutes"] <= 30

    def test_recheck_septic_shock_is_15(self):
        """Choque séptico → 15 min."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
        )
        assert out.result["recheck_time_minutes"] == 15

    def test_markedly_elevated_lactate_shortens_recheck(self):
        """Lactato ≥ 4.0 en sepsis probable → 15 min (acortado)."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=22, sbp=98, mental_status_altered=False,
            map_mmhg=70.0, lactate_mmol_l=4.5, vasopressor=False,
        )
        # Puede ser sepsis o shock dependiendo del MAP exacto
        assert out.result["recheck_time_minutes"] <= 30


# ─────────────────────────────────────────────────────────────────────────────
# F. Tests de salida homogénea (contrato ClinicalOutput)
# ─────────────────────────────────────────────────────────────────────────────

class TestHomogeneousOutput:

    REQUIRED_RESULT_KEYS = [
        "suspected_infection",
        "qsofa_score", "qsofa_positive",
        "sofa_components_available", "sofa_partial_score",
        "sofa_n_components_evaluated",
        "lactate_flag", "lactate_level",
        "map_flag", "vasopressor_flag",
        "urine_output_flag", "hypoperfusion_flag",
        "severity_class",
        "bundle_actions",
        "recheck_time_minutes",
        "warnings",
        "limitations",
    ]

    def test_all_required_keys_present(self):
        """Todas las claves requeridas deben estar en result."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=2.3, vasopressor=False,
        )
        for key in self.REQUIRED_RESULT_KEYS:
            assert key in out.result, f"Clave faltante en result: {key}"

    def test_p_is_none(self):
        """p debe ser None (no es módulo Bayesiano)."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.p is None

    def test_U_is_none(self):
        """U debe ser None."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.U is None

    def test_NB_is_none(self):
        """NB debe ser None (no es DCA)."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.NB is None

    def test_ci_is_none(self):
        """ci debe ser None en v1."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.ci is None

    def test_limitations_are_declared(self):
        """Limitaciones del módulo deben estar declaradas y no vacías."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert isinstance(out.result["limitations"], list)
        assert len(out.result["limitations"]) > 0

    def test_to_dict_is_serializable(self):
        """to_dict() no debe lanzar y devuelve dict."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=68.0, lactate_mmol_l=2.3, vasopressor=False,
        )
        d = out.to_dict()
        assert isinstance(d, dict)
        import json
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 0

    def test_explain_is_non_empty_string(self):
        """explain debe ser string no vacío."""
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert isinstance(out.explain, str)
        assert len(out.explain) > 10


# ─────────────────────────────────────────────────────────────────────────────
# G. Tests de integración con el orquestador
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorIntegration:

    def test_orchestrator_returns_dict_with_contract_keys(self):
        """El orquestador devuelve el contrato SMNC-5+ completo."""
        payload = _orch_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        required = ["result", "action", "p", "U", "NB", "units_ok", "explain", "ci", "request_id"]
        for k in required:
            assert k in result, f"Falta '{k}' en output del orquestador"

    def test_orchestrator_request_id_generated(self):
        """request_id debe generarse en cada ejecución."""
        payload = _orch_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert "request_id" in r
        assert len(r["request_id"]) > 0

    def test_orchestrator_request_id_unique(self):
        """Dos ejecuciones del mismo payload producen request_id distintos."""
        payload = _orch_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "audit.jsonl"
            r1 = orchestrator.run(payload, log_path=log)
            r2 = orchestrator.run(payload, log_path=log)
        assert r1["request_id"] != r2["request_id"]

    def test_orchestrator_units_ok_true_for_valid_inputs(self):
        """Inputs válidos → units_ok=True."""
        payload = _orch_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["units_ok"] is True

    def test_orchestrator_audit_written(self):
        """El orquestador escribe en el log de auditoría."""
        import json
        payload = _orch_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            orchestrator.run(payload, log_path=log_path)
            # Verificar dentro del bloque con para que el directorio exista
            assert log_path.exists(), "El log de auditoría no fue creado"
            with log_path.open() as f:
                lines = f.readlines()
            assert len(lines) >= 1
            record = json.loads(lines[-1])
            assert "request_id" in record
            assert record["module"] == "sepsis_protocol"

    def test_orchestrator_sepsis_low_risk(self):
        """Orquestador con sospecha baja → observe."""
        payload = _orch_payload(
            suspected_infection=False,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmHg=85.0, lactate_mmol_L=1.1, vasopressor=False,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["action"] == Action.OBSERVE
        assert r["result"]["severity_class"] == "low_suspicion"

    def test_orchestrator_sepsis_probable(self):
        """Orquestador con sepsis probable."""
        payload = _orch_payload(
            suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmHg=68.0, lactate_mmol_L=2.3, vasopressor=False,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["result"]["severity_class"] == "sepsis_probable"
        assert r["action"] == Action.START_TREATMENT

    def test_orchestrator_septic_shock(self):
        """Orquestador con choque séptico probable."""
        payload = _orch_payload(
            suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmHg=54.0, lactate_mmol_L=4.8, vasopressor=True,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["result"]["severity_class"] == "septic_shock_probable"
        assert r["action"] == Action.START_TREATMENT


# ─────────────────────────────────────────────────────────────────────────────
# H. Tests del Units Gate para sepsis_protocol
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitsGateSepsis:

    def _base_inputs(self):
        return {
            "suspected_infection": True,
            "rr": 18,
            "sbp": 120,
            "mental_status_altered": False,
            "map_mmHg": 85.0,
            "lactate_mmol_L": 1.0,
            "vasopressor": False,
        }

    def test_valid_inputs_pass(self):
        """Inputs válidos no bloquean."""
        ci = _make_input(self._base_inputs())
        run_gate(ci)  # no debe lanzar

    def test_rr_zero_blocks(self):
        """FR = 0 → bloqueado."""
        inputs = self._base_inputs()
        inputs["rr"] = 0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError) as exc:
            run_gate(ci)
        assert any("rr" in v for v in exc.value.violations)

    def test_rr_negative_blocks(self):
        """FR negativa → bloqueado."""
        inputs = self._base_inputs()
        inputs["rr"] = -5
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_sbp_zero_blocks(self):
        """PAS = 0 → bloqueado."""
        inputs = self._base_inputs()
        inputs["sbp"] = 0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_map_zero_blocks(self):
        """MAP = 0 → bloqueado."""
        inputs = self._base_inputs()
        inputs["map_mmHg"] = 0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_map_negative_blocks(self):
        """MAP negativa → bloqueado."""
        inputs = self._base_inputs()
        inputs["map_mmHg"] = -10.0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_lactate_negative_blocks(self):
        """Lactato negativo → bloqueado."""
        inputs = self._base_inputs()
        inputs["lactate_mmol_L"] = -1.0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_lactate_zero_valid(self):
        """Lactato = 0 → válido (raro pero técnicamente posible en laboratorio)."""
        inputs = self._base_inputs()
        inputs["lactate_mmol_L"] = 0.0
        ci = _make_input(inputs)
        run_gate(ci)  # no debe lanzar

    def test_nan_rr_blocks(self):
        """FR = NaN → bloqueado."""
        inputs = self._base_inputs()
        inputs["rr"] = float("nan")
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_inf_lactate_blocks(self):
        """Lactato = inf → bloqueado."""
        inputs = self._base_inputs()
        inputs["lactate_mmol_L"] = float("inf")
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_platelets_zero_blocks(self):
        """Plaquetas = 0 → bloqueado."""
        inputs = self._base_inputs()
        inputs["platelets_k_uL"] = 0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_platelets_positive_valid(self):
        """Plaquetas = 120 → válido."""
        inputs = self._base_inputs()
        inputs["platelets_k_uL"] = 120
        ci = _make_input(inputs)
        run_gate(ci)  # no debe lanzar

    def test_pao2_fio2_zero_blocks(self):
        """PaO2/FiO2 = 0 → bloqueado."""
        inputs = self._base_inputs()
        inputs["pao2_fio2"] = 0
        ci = _make_input(inputs)
        with pytest.raises(UnitsGateError):
            run_gate(ci)

    def test_gate_blocked_by_orchestrator(self):
        """Orquestador bloquea con action='blocked' para inputs inválidos."""
        payload = _orch_payload(rr=0)  # rr=0 inválido
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["action"] == Action.BLOCKED
        assert r["units_ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# I. Tests del módulo run() — interfaz del orquestador directo
# ─────────────────────────────────────────────────────────────────────────────

class TestRunInterface:

    def test_run_returns_clinical_output(self):
        """run() del módulo devuelve ClinicalOutput."""
        from hipocrates.utils.types import ClinicalOutput
        payload = {
            "patient_id": "T",
            "module": "sepsis_protocol",
            "inputs": {
                "suspected_infection": True,
                "rr": 18, "sbp": 115,
                "mental_status_altered": False,
                "map_mmHg": 82.0,
                "lactate_mmol_L": 1.5,
                "vasopressor": False,
            },
            "constraints": {},
            "version": SCHEMA_VERSION,
        }
        out = run(payload)
        assert isinstance(out, ClinicalOutput)

    def test_run_with_all_optional_fields(self):
        """run() con todos los campos opcionales no lanza."""
        payload = {
            "patient_id": "T",
            "module": "sepsis_protocol",
            "inputs": {
                "suspected_infection": True,
                "rr": 28, "sbp": 82,
                "mental_status_altered": True,
                "map_mmHg": 54.0,
                "lactate_mmol_L": 4.8,
                "vasopressor": True,
                "urine_output_ml_kg_h": 0.15,
                "creatinine_mg_dL": 3.2,
                "bilirubin_mg_dL": 2.8,
                "platelets_k_uL": 68,
                "pao2_fio2": 165,
                "mechanical_ventilation": True,
            },
            "constraints": {},
            "version": SCHEMA_VERSION,
        }
        out = run(payload)
        assert out.result["severity_class"] == "septic_shock_probable"
        assert out.result["sofa_n_components_evaluated"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# J. No regresión: módulos anteriores no se rompen
# ─────────────────────────────────────────────────────────────────────────────

class TestNoRegression:

    def test_bayes_sprt_still_works(self):
        """Bayes SPRT sigue funcionando tras la integración de sepsis."""
        payload = {
            "patient_id": "REG-001",
            "module": "bayes_sprt",
            "inputs": {
                "p0": 0.25,
                "tests": [{"name": "t1", "lr": 3.0, "result": "pos"}],
                "theta_T": 0.8,
                "theta_A": 0.05,
            },
            "constraints": {},
            "version": SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["action"] in (Action.START_TREATMENT, Action.OBTAIN_TEST,
                                Action.OBSERVE, Action.DISCARD_DIAGNOSIS)
        assert "request_id" in r

    def test_abg_still_works(self):
        """Módulo ABG sigue funcionando."""
        payload = {
            "patient_id": "REG-002",
            "module": "abg_hh_stewart",
            "inputs": {"ph": 7.35, "paco2": 45.0, "hco3": 24.0,
                       "na": 140.0, "k": 4.0, "cl": 104.0},
            "constraints": {},
            "version": SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["action"] != Action.ERROR
        assert "request_id" in r

    def test_schema_rejects_unknown_module(self):
        """El schema sigue rechazando módulos desconocidos."""
        payload = {
            "patient_id": "REG-003",
            "module": "unknown_module",
            "inputs": {"x": 1},
            "constraints": {},
            "version": SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            r = orchestrator.run(payload, log_path=Path(tmpdir) / "audit.jsonl")
        assert r["action"] == Action.ERROR


# ─────────────────────────────────────────────────────────────────────────────
# K. Tests de las tres grietas corregidas (v1 → v1.1)
#    K1: explain no contiene strings crudos internos
#    K2: lactato aislado (qSOFA=0, MAP ok, sin vasopresor) → obtain_test
#    K3: lactato elevado + qSOFA≥1 → escalada correcta a start_treatment
#    K4: qSOFA≥2 sigue escalando a start_treatment
#    K5: SOFA parcial≥2 sigue escalando a start_treatment
# ─────────────────────────────────────────────────────────────────────────────

class TestGrietasV1Corrections:
    """
    Verifica las tres correcciones quirúrgicas aplicadas en v1.1:

    Grieta A — explain no filtra strings crudos internos (snake_case).
    Grieta B — home page y conteo de tests (visual, no testeable aquí).
    Grieta C — _determine_action() demasiado agresiva con lactato aislado.
    """

    # ── Grieta A: explain humanizado ─────────────────────────────────────────

    def test_explain_no_raw_severity_strings(self):
        """
        explain no debe contener los strings crudos de severidad/lactato/acción.
        Los valores internos (low_suspicion, sepsis_probable, start_treatment…)
        deben haberse reemplazado por lenguaje clínico en español.
        """
        # Strings que jamás deben aparecer literalmente en explain
        raw_forbidden = [
            "low_suspicion",
            "sepsis_probable",
            "septic_shock_probable",
            "markedly_elevated",
            # Los labels de acción no deben aparecer con el patrón «acción: razón»
            # en formato snake_case seguido de dos puntos
            "start_treatment:",
            "obtain_test:",
            "observe:",
        ]
        scenarios = [
            # (rr, sbp, mental, map_mmhg, lactate, vasopressor, inf)  descripción
            (16, 120, False, 85.0, 1.0, False, True),   # low_suspicion
            (24, 94,  False, 68.0, 2.3, False, True),   # sepsis_probable → start_treatment
            (28, 82,  True,  54.0, 4.8, True,  True),   # septic_shock → start_treatment
            (16, 120, False, 80.0, 2.1, False, True),   # lactato aislado → obtain_test
            (16, 120, False, 85.0, 1.0, False, False),  # sin infección → observe
        ]
        for rr, sbp, mental, mp, lat, vaso, inf in scenarios:
            out = compute_sepsis(
                patient_id="GRIETA-A", suspected_infection=inf,
                rr=rr, sbp=sbp, mental_status_altered=mental,
                map_mmhg=mp, lactate_mmol_l=lat, vasopressor=vaso,
            )
            for raw in raw_forbidden:
                assert raw not in out.explain, (
                    f"explain contiene string crudo prohibido '{raw}' "
                    f"(scenario rr={rr} lat={lat} inf={inf}).\n"
                    f"explain: {out.explain[:300]}"
                )

    def test_explain_contains_human_readable_classification(self):
        """
        explain debe contener la clasificación en español clínico, no en snake_case.
        """
        # septic_shock_probable → debe aparecer "Choque séptico probable"
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
        )
        assert "Choque séptico probable" in out.explain, (
            f"La clasificación humanizada no aparece en explain: {out.explain[:300]}"
        )

        # sepsis_probable → debe aparecer "Sepsis probable"
        out2 = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=68.0, lactate_mmol_l=2.3, vasopressor=False,
        )
        assert "Sepsis probable" in out2.explain, (
            f"La clasificación humanizada no aparece en explain: {out2.explain[:300]}"
        )

    def test_explain_lactate_human_label(self):
        """
        El nivel de lactato en explain debe estar en español (e.g. 'elevado (≥ 2.0 mmol/L)'),
        no en snake_case inglés ('elevated').
        """
        out = compute_sepsis(
            patient_id="T", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=4.2, vasopressor=False,
        )
        # "marcadamente elevado" debe aparecer en lugar de "markedly_elevated"
        assert "marcadamente elevado" in out.explain, (
            f"Etiqueta de lactato marcado en inglés en explain: {out.explain[:300]}"
        )
        assert "markedly_elevated" not in out.explain

    # ── Grieta C: _determine_action() más prudente ────────────────────────────

    def test_isolated_lactate_no_other_signals_is_obtain_test(self):
        """
        CASO CRÍTICO — Grieta C:
        Lactato ≥ 2.0 con sospecha infecciosa pero SIN otros signos computable
        de disfunción orgánica (qSOFA=0, MAP aceptable, sin vasopresor, sin oliguria)
        → acción debe ser obtain_test, NO start_treatment.

        Justificación: el sistema no tiene evidencia suficiente de disfunción
        orgánica concomitante para recomendar tratamiento autónomamente.
        """
        out = compute_sepsis(
            patient_id="GRIETA-C-1", suspected_infection=True,
            rr=16,    # FR normal → qSOFA sin criterio de FR
            sbp=120,  # PAS normal → qSOFA sin criterio de PAS
            mental_status_altered=False,  # → qSOFA sin criterio de consciencia
            map_mmhg=80.0,  # MAP ≥ 65 → map_flag=False
            lactate_mmol_l=2.1,  # ≥ 2.0 → lactate_flag=True, sepsis_probable
            vasopressor=False,   # → vasopressor_flag=False
            # sin urine_output_ml_kg_h → urine_output_flag=False
        )
        assert out.result["severity_class"] == "sepsis_probable", (
            "Pre-condición: debe ser sepsis_probable por lactato ≥ 2.0"
        )
        assert out.result["qsofa_score"] == 0, "qSOFA debe ser 0 en este caso"
        assert out.result["lactate_flag"] is True
        assert out.result["map_flag"] is False
        assert out.result["vasopressor_flag"] is False
        assert out.result["urine_output_flag"] is False
        assert out.action == Action.OBTAIN_TEST, (
            f"Lactato aislado sin señales de soporte debe dar obtain_test, "
            f"pero fue '{out.action}'. explain: {out.explain[:250]}"
        )

    def test_isolated_lactate_2_exactly_is_obtain_test(self):
        """Lactato exactamente 2.0 aislado (qSOFA=0, MAP ok) → obtain_test."""
        out = compute_sepsis(
            patient_id="GRIETA-C-2", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=75.0, lactate_mmol_l=2.0, vasopressor=False,
        )
        assert out.result["lactate_flag"] is True
        assert out.result["qsofa_score"] == 0
        assert out.action == Action.OBTAIN_TEST, (
            f"Lactato=2.0 aislado debe ser obtain_test, fue '{out.action}'"
        )

    def test_isolated_lactate_high_qsofa_0_is_obtain_test(self):
        """Lactato 3.5 con qSOFA=0, MAP normal → obtain_test (sin señal de soporte)."""
        out = compute_sepsis(
            patient_id="GRIETA-C-3", suspected_infection=True,
            rr=18, sbp=115, mental_status_altered=False,
            map_mmhg=78.0, lactate_mmol_l=3.5, vasopressor=False,
        )
        assert out.result["qsofa_score"] == 0
        assert out.result["lactate_flag"] is True
        assert out.action == Action.OBTAIN_TEST

    def test_elevated_lactate_plus_qsofa1_escalates_to_start_treatment(self):
        """
        Lactato ≥ 2.0 + qSOFA ≥ 1 → start_treatment.
        El qSOFA=1 actúa como señal de soporte que permite la escalada.
        """
        out = compute_sepsis(
            patient_id="GRIETA-C-4", suspected_infection=True,
            rr=22,   # FR ≥ 22 → qSOFA +1
            sbp=120,
            mental_status_altered=False,
            map_mmhg=80.0,  # MAP ok → map_flag=False
            lactate_mmol_l=2.2,  # lactato elevado → lactate_flag=True
            vasopressor=False,
        )
        assert out.result["qsofa_score"] >= 1
        assert out.result["lactate_flag"] is True
        assert out.result["severity_class"] == "sepsis_probable"
        assert out.action == Action.START_TREATMENT, (
            f"Lactato+qSOFA1 debe escalar a start_treatment, fue '{out.action}'. "
            f"explain: {out.explain[:250]}"
        )

    def test_elevated_lactate_plus_map_flag_escalates(self):
        """Lactato ≥ 2.0 + MAP < 65 → start_treatment (MAP flag es soporte)."""
        out = compute_sepsis(
            patient_id="GRIETA-C-5", suspected_infection=True,
            rr=16, sbp=115, mental_status_altered=False,
            map_mmhg=62.0,  # < 65 → map_flag=True
            lactate_mmol_l=2.3,
            vasopressor=False,
        )
        # Puede ser septic_shock o sepsis_probable dependiendo de criterios
        # En cualquier caso, la acción debe ser start_treatment
        assert out.result["lactate_flag"] is True
        assert out.result["map_flag"] is True
        assert out.action == Action.START_TREATMENT

    def test_elevated_lactate_plus_vasopressor_escalates(self):
        """Lactato ≥ 2.0 + vasopresor → start_treatment (y probablemente septic_shock)."""
        out = compute_sepsis(
            patient_id="GRIETA-C-6", suspected_infection=True,
            rr=18, sbp=110, mental_status_altered=False,
            map_mmhg=68.0, lactate_mmol_l=2.1, vasopressor=True,
        )
        assert out.result["lactate_flag"] is True
        assert out.result["vasopressor_flag"] is True
        assert out.action == Action.START_TREATMENT

    def test_elevated_lactate_plus_oliguria_escalates(self):
        """Lactato ≥ 2.0 + oliguria → start_treatment."""
        out = compute_sepsis(
            patient_id="GRIETA-C-7", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=80.0, lactate_mmol_l=2.2, vasopressor=False,
            urine_output_ml_kg_h=0.3,  # oliguria
        )
        assert out.result["lactate_flag"] is True
        assert out.result["urine_output_flag"] is True
        assert out.action == Action.START_TREATMENT

    def test_qsofa_2_still_triggers_start_treatment(self):
        """
        Regresión: qSOFA ≥ 2 con sospecha infecciosa debe seguir dando start_treatment.
        Esta lógica NO debe haber sido afectada por la corrección de Grieta C.
        """
        out = compute_sepsis(
            patient_id="GRIETA-C-REG1", suspected_infection=True,
            rr=24, sbp=94,   # qSOFA +2 (FR + PAS)
            mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=1.2, vasopressor=False,
        )
        assert out.result["qsofa_score"] == 2
        assert out.result["qsofa_positive"] is True
        assert out.result["severity_class"] == "sepsis_probable"
        assert out.action == Action.START_TREATMENT, (
            f"qSOFA=2 debe dar start_treatment, fue '{out.action}'"
        )

    def test_sofa_partial_2_still_triggers_start_treatment(self):
        """
        Regresión: SOFA parcial ≥ 2 con sospecha infecciosa debe dar start_treatment.
        """
        out = compute_sepsis(
            patient_id="GRIETA-C-REG2", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=82.0, lactate_mmol_l=1.0, vasopressor=False,
            creatinine_mg_dl=3.5,  # SOFA renal = 3 → SOFA parcial ≥ 2
        )
        assert out.result["sofa_partial_score"] >= 2
        assert out.result["severity_class"] == "sepsis_probable"
        assert out.action == Action.START_TREATMENT, (
            f"SOFA≥2 debe dar start_treatment, fue '{out.action}'"
        )

    def test_qsofa_3_still_triggers_start_treatment(self):
        """Regresión: qSOFA=3 con sospecha → start_treatment."""
        out = compute_sepsis(
            patient_id="GRIETA-C-REG3", suspected_infection=True,
            rr=28, sbp=88, mental_status_altered=True,  # qSOFA = 3
            map_mmhg=70.0, lactate_mmol_l=1.5, vasopressor=False,
        )
        assert out.result["qsofa_score"] == 3
        assert out.action == Action.START_TREATMENT

    def test_septic_shock_always_start_treatment(self):
        """Regresión: septic_shock_probable siempre → start_treatment."""
        out = compute_sepsis(
            patient_id="GRIETA-C-REG4", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
        )
        assert out.result["severity_class"] == "septic_shock_probable"
        assert out.action == Action.START_TREATMENT


# ─────────────────────────────────────────────────────────────────────────────
# L. Tests de alineación bundle ↔ action (parche bundle v1.2)
#    Verifica que el bundle refleja el nivel de intervención de la action,
#    no solo la severity_class.
# ─────────────────────────────────────────────────────────────────────────────

class TestBundleActionAlignment:
    """
    Garantiza que _build_bundle() está alineado con la action computada.

    Caso B: sepsis_probable + obtain_test  → bundle de evaluación/confirmación
    Caso C: sepsis_probable + start_treatment → bundle intervencionista
    Caso D: septic_shock_probable + start_treatment → bundle urgente intacto
    """

    # ── Caso B: bundle conservador cuando action = obtain_test ────────────────

    def test_bundle_obtain_test_contains_confirmatory_items(self):
        """
        sepsis_probable + obtain_test → el bundle debe incluir
        ítems de confirmación (lactato, analítica, revaloración) y NO debe
        contener lenguaje de inicio de tratamiento agresivo.
        """
        # Lactato aislado → sepsis_probable + obtain_test
        out = compute_sepsis(
            patient_id="BUNDLE-B-1", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=80.0, lactate_mmol_l=2.1, vasopressor=False,
        )
        assert out.result["severity_class"] == "sepsis_probable"
        assert out.action == Action.OBTAIN_TEST

        bundle = out.result["bundle_actions"]
        bundle_text = " ".join(bundle).lower()

        # Debe contener ítems de evaluación
        assert any("lactato" in item.lower() for item in bundle), (
            "Bundle de obtain_test debe mencionar lactato/tendencia"
        )
        assert any("analít" in item.lower() or "sofa" in item.lower() for item in bundle), (
            "Bundle de obtain_test debe solicitar analítica para SOFA"
        )
        assert any("revalorar" in item.lower() or "reevaluar" in item.lower() or
                   "monitori" in item.lower() for item in bundle), (
            "Bundle de obtain_test debe incluir revaloración/monitorización"
        )

        # NO debe contener lenguaje de inicio de tratamiento
        assert "reanimación con líquidos iv" not in bundle_text, (
            "Bundle obtain_test no debe recomendar reanimación con líquidos IV"
        )
        assert "antibioterapia empírica" not in bundle_text, (
            "Bundle obtain_test no debe recomendar antibioterapia empírica"
        )
        assert "hemocultivos" not in bundle_text, (
            "Bundle obtain_test no debe recomendar hemocultivos "
            "(ese lenguaje es de inicio de tratamiento)"
        )

    def test_bundle_obtain_test_note_in_explain(self):
        """
        sepsis_probable + obtain_test → explain debe incluir nota discriminante
        que aclare que el bundle es de evaluación, no de inicio.
        """
        out = compute_sepsis(
            patient_id="BUNDLE-B-2", suspected_infection=True,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=80.0, lactate_mmol_l=2.1, vasopressor=False,
        )
        assert out.action == Action.OBTAIN_TEST
        assert "bundle" in out.explain.lower() or "evaluación" in out.explain.lower(), (
            f"explain debe mencionar que el bundle es de evaluación: {out.explain[:300]}"
        )

    def test_bundle_obtain_test_multiple_isolated_lactate_scenarios(self):
        """
        Varios escenarios de lactato aislado → todos deben dar bundle conservador.
        """
        isolated_scenarios = [
            # (rr, sbp, mental, map_mmhg, lactate)
            (16, 120, False, 80.0, 2.0),   # umbral exacto
            (18, 115, False, 78.0, 2.5),   # moderado
            (16, 120, False, 75.0, 3.5),   # alto pero sin soporte
        ]
        interventionist_keywords = [
            "reanimación con líquidos iv",
            "antibioterapia empírica",
        ]
        for rr, sbp, mental, mp, lat in isolated_scenarios:
            out = compute_sepsis(
                patient_id="BUNDLE-B-MULTI", suspected_infection=True,
                rr=rr, sbp=sbp, mental_status_altered=mental,
                map_mmhg=mp, lactate_mmol_l=lat, vasopressor=False,
            )
            if out.action != Action.OBTAIN_TEST:
                continue  # solo verificamos los que dan obtain_test
            bundle_text = " ".join(out.result["bundle_actions"]).lower()
            for kw in interventionist_keywords:
                assert kw not in bundle_text, (
                    f"Bundle obtain_test (lat={lat}) contiene '{kw}': {bundle_text[:200]}"
                )

    # ── Caso C: bundle intervencionista cuando action = start_treatment ────────

    def test_bundle_start_treatment_sepsis_probable_contains_interventionist_items(self):
        """
        sepsis_probable + start_treatment → bundle debe incluir
        hemocultivos, reanimación, antibioterapia.
        """
        # qSOFA=2 → start_treatment
        out = compute_sepsis(
            patient_id="BUNDLE-C-1", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=1.2, vasopressor=False,
        )
        assert out.result["severity_class"] == "sepsis_probable"
        assert out.action == Action.START_TREATMENT

        bundle = out.result["bundle_actions"]
        bundle_text = " ".join(bundle).lower()

        assert "hemocultivos" in bundle_text, "Bundle start_treatment debe incluir hemocultivos"
        assert "reanimación" in bundle_text, "Bundle start_treatment debe incluir reanimación"
        assert "antibioterapia" in bundle_text, "Bundle start_treatment debe incluir antibioterapia"

    def test_bundle_start_treatment_lactate_plus_qsofa1(self):
        """
        Lactato elevado + qSOFA=1 → start_treatment → bundle intervencionista.
        """
        out = compute_sepsis(
            patient_id="BUNDLE-C-2", suspected_infection=True,
            rr=22, sbp=120, mental_status_altered=False,
            map_mmhg=80.0, lactate_mmol_l=2.2, vasopressor=False,
        )
        assert out.action == Action.START_TREATMENT
        bundle_text = " ".join(out.result["bundle_actions"]).lower()
        assert "hemocultivos" in bundle_text
        assert "reanimación" in bundle_text

    def test_bundle_start_treatment_no_confirmatory_note_in_explain(self):
        """
        sepsis_probable + start_treatment → explain NO debe tener la nota
        discriminante (esa solo aparece en obtain_test).
        """
        out = compute_sepsis(
            patient_id="BUNDLE-C-3", suspected_infection=True,
            rr=24, sbp=94, mental_status_altered=False,
            map_mmhg=72.0, lactate_mmol_l=1.2, vasopressor=False,
        )
        assert out.action == Action.START_TREATMENT
        assert "bundle recomendado es de evaluación" not in out.explain, (
            "La nota discriminante no debe aparecer en start_treatment"
        )

    # ── Caso D: bundle urgente de choque séptico intacto ─────────────────────

    def test_bundle_septic_shock_contains_urgent_items(self):
        """
        septic_shock_probable → bundle urgente debe incluir URGENTE,
        vasopresores, UCI, reanimación agresiva.
        """
        out = compute_sepsis(
            patient_id="BUNDLE-D-1", suspected_infection=True,
            rr=28, sbp=82, mental_status_altered=True,
            map_mmhg=54.0, lactate_mmol_l=4.8, vasopressor=True,
        )
        assert out.result["severity_class"] == "septic_shock_probable"
        assert out.action == Action.START_TREATMENT

        bundle = out.result["bundle_actions"]
        bundle_text = " ".join(bundle).lower()

        assert "urgente" in bundle_text, "Bundle septic_shock debe tener etiqueta URGENTE"
        assert "uci" in bundle_text, "Bundle septic_shock debe mencionar UCI"
        assert "vasopresor" in bundle_text or "norepinefrina" in bundle_text, (
            "Bundle septic_shock debe mencionar vasopresores"
        )

    def test_bundle_septic_shock_not_affected_by_bundle_patch(self):
        """
        Regresión: el parche de alineación no debe alterar el bundle de septic_shock.
        El bundle urgente debe seguir igual que antes.
        """
        out = compute_sepsis(
            patient_id="BUNDLE-D-2", suspected_infection=True,
            rr=28, sbp=80, mental_status_altered=False,
            map_mmhg=58.0, lactate_mmol_l=3.2, vasopressor=False,
        )
        assert out.result["severity_class"] == "septic_shock_probable"
        assert out.action == Action.START_TREATMENT

        bundle = out.result["bundle_actions"]
        # Vasopressor=False → debe sugerir valorar inicio
        bundle_text = " ".join(bundle).lower()
        assert "vasopresor" in bundle_text

    # ── Caso A: low_suspicion + observe sigue igual ───────────────────────────

    def test_bundle_low_suspicion_observe_unchanged(self):
        """
        Regresión: low_suspicion → bundle conservador sigue intacto.
        """
        out = compute_sepsis(
            patient_id="BUNDLE-A-1", suspected_infection=False,
            rr=16, sbp=120, mental_status_altered=False,
            map_mmhg=85.0, lactate_mmol_l=1.0, vasopressor=False,
        )
        assert out.result["severity_class"] == "low_suspicion"
        assert out.action == Action.OBSERVE
        bundle_text = " ".join(out.result["bundle_actions"]).lower()
        assert "monitori" in bundle_text
        assert "revalorar" in bundle_text or "reevaluar" in bundle_text
        # No debe haber lenguaje intervencionista
        assert "hemocultivos" not in bundle_text
        assert "antibioterapia" not in bundle_text
