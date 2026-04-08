"""
test_abg_hh_stewart.py — Tests del ABG_HH_Stewart_Engine.

Cubre:
  - acidosis metabólica simple detectada correctamente
  - alcalosis respiratoria detectada
  - caso con compensación Winter: adecuada vs inadecuada
  - AG elevado detectado
  - AG corregido por albúmina
  - consistencia H–H (pH medido vs calculado)
  - salida estructurada homogénea
"""

import math
import pytest

from hipocrates.modules.abg_hh_stewart import run_abg, run


# ── Acidosis metabólica ───────────────────────────────────────────────────────

class TestAcidosisMetabolica:
    def test_primary_disorder_detected(self):
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert out.result["primary_disorder"] == "acidosis_metabolica"

    def test_action_is_string(self):
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert isinstance(out.action, str)
        assert out.action != ""

    def test_consistency_ok_when_close(self):
        """pH medido y H–H calculado deben ser consistentes (discrepancia < 0.05)."""
        # pH calculado para paco2=40, hco3=24: ~7.4
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0)
        assert out.result["consistency_ok"] is True

    def test_ag_calculated(self):
        """AG = Na - (Cl + HCO3) = 138 - (108 + 14.5) = 15.5"""
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert math.isclose(out.result["anion_gap"], 15.5, abs_tol=0.01)

    def test_ag_corrected_by_albumin(self):
        """AGcorr = AG + 2.5*(4.0 - Alb). Con Alb=3.8: +0.5"""
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0,
                      albumin_g_dl=3.8)
        expected_agcorr = 15.5 + 2.5 * (4.0 - 3.8)
        assert math.isclose(out.result["anion_gap_corrected"], expected_agcorr, abs_tol=0.01)

    def test_winter_range_present(self):
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        w = out.result["winter_expected_paco2"]
        assert "lo" in w and "hi" in w
        # Winter: 1.5*14.5 + 8 ± 2 = [27.75, 31.75]
        # El output redondea a 1 decimal → tolerancia 0.1
        assert math.isclose(w["lo"], 1.5 * 14.5 + 8 - 2, abs_tol=0.1)
        assert math.isclose(w["hi"], 1.5 * 14.5 + 8 + 2, abs_tol=0.1)


# ── Compensación respiratoria (Winter) ───────────────────────────────────────

class TestCompensacion:
    def test_adequate_compensation(self):
        """paco2=29.75 cae dentro del rango Winter para hco3=14.5 → adecuada."""
        # Winter center = 1.5*14.5+8 = 29.75; rango [27.75, 31.75]
        out = run_abg(ph=7.28, paco2=29.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert out.result["compensation"] == "compensacion_respiratoria_adecuada"

    def test_inadequate_compensation_above_range(self):
        """paco2=40 está por encima del rango Winter → hipoventilación concomitante."""
        out = run_abg(ph=7.25, paco2=40.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert "hipoventilacion" in out.result["compensation"]


# ── Alcalosis respiratoria ────────────────────────────────────────────────────

class TestAlcalosisRespiratoria:
    def test_detected(self):
        out = run_abg(ph=7.52, paco2=28.0, hco3=22.0,
                      na=140.0, k=3.8, cl=104.0)
        assert out.result["primary_disorder"] == "alcalosis_respiratoria"


# ── pH normal ────────────────────────────────────────────────────────────────

class TestPhNormal:
    def test_normal_ph(self):
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0)
        assert out.result["primary_disorder"] == "ph_normal"


# ── Salida estructurada ───────────────────────────────────────────────────────

class TestOutputStructure:
    def test_all_required_fields_present(self):
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        required = [
            "ph_measured", "ph_calculated_hh", "ph_discrepancy", "consistency_ok",
            "paco2", "hco3", "anion_gap", "anion_gap_corrected", "ag_elevated",
            "delta_delta", "winter_expected_paco2", "SIDa", "Atot",
            "primary_disorder", "compensation", "formal_label", "stewart_note",
        ]
        for field in required:
            assert field in out.result, f"Campo faltante: {field}"

    def test_units_ok_true(self):
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0)
        assert out.units_ok is True

    def test_explain_is_nonempty_string(self):
        out = run_abg(ph=7.28, paco2=32.0, hco3=14.5,
                      na=138.0, k=4.2, cl=108.0)
        assert isinstance(out.explain, str) and len(out.explain) > 20

    def test_p_is_none_for_abg(self):
        """ABG no produce probabilidad posterior."""
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0)
        assert out.p is None


# ── SIDa y Atot ──────────────────────────────────────────────────────────────

class TestStewart:
    def test_sida_calculated(self):
        """SIDa = (140+4+5+1.8) - (104+1) = 150.8 - 105 = 45.8"""
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0,
                      ca_meq_l=5.0, mg_meq_l=1.8, lactate_meq_l=1.0)
        expected = (140 + 4 + 5 + 1.8) - (104 + 1)
        assert math.isclose(out.result["SIDa"], expected, abs_tol=0.01)

    def test_atot_calculated(self):
        """Atot = 2.43*4.0 + 0.097*3.5 = 9.72 + 0.3395 = 10.06"""
        out = run_abg(ph=7.40, paco2=40.0, hco3=24.0,
                      na=140.0, k=4.0, cl=104.0,
                      albumin_g_dl=4.0, phosphate_mg_dl=3.5)
        expected = 2.43 * 4.0 + 0.097 * 3.5
        assert math.isclose(out.result["Atot"], expected, abs_tol=0.01)


# ── Interface estándar (run) ──────────────────────────────────────────────────

class TestRunInterface:
    def test_run_returns_clinical_output(self):
        payload = {
            "patient_id": "T",
            "module": "abg_hh_stewart",
            "inputs": {
                "ph": 7.35, "paco2": 45.0, "hco3": 24.0,
                "na": 138.0, "k": 4.2, "cl": 104.0,
            },
            "constraints": {},
            "version": "SMNC-5+_v1.0",
        }
        out = run(payload)
        assert isinstance(out.result, dict)
        assert "primary_disorder" in out.result
