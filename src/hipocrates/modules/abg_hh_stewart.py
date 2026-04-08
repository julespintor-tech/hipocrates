"""
abg_hh_stewart.py — ABG_HH_Stewart_Engine

Motor de interpretación ácido–base (SMNC-5+, §2.2 + §6.5).

Implementa:
  1. Henderson–Hasselbalch: pH = pKa + log([HCO3-] / (0.0307 × PaCO2))
  2. Anion Gap (AG): Na+ − (Cl− + HCO3−)
  3. AG corregido por albúmina: AG_corr = AG + 2.5 × (4.0 − Alb_g/dL)
  4. Delta-delta: (AG − 12) / (24 − HCO3)   [detección de trastornos mixtos]
  5. Winter (compensación respiratoria en acidosis metabólica):
       PaCO2_esperada = 1.5 × HCO3 + 8 ± 2
  6. SIDa (Stewart aparente): Na+ + K+ + Ca²+ + Mg²+ − Cl− − lactato
  7. Atot: aproximación = 2.43 × Alb(g/dL) + 0.097 × Fosfato(mg/dL)   [Watson]
  8. Diagnóstico textual primario + compensación

Limitaciones explícitas:
  - Requiere unidades SI / convencionales indicadas en los docstrings.
  - La consistencia Stewart completa (resolver pH numéricamente) está
    aproximada: se usa SIDa para caracterización cualitativa, no resolución
    numérica completa. El sistema lo indica claramente.
  - No es un reemplazo de gasometría clínica.

Dominios de validez:
  - pH: 6.5 – 8.0
  - PaCO2: 5 – 120 mmHg
  - HCO3−: 1 – 60 mEq/L

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from hipocrates.utils.types import Action, ClinicalOutput

# Constantes fisicoquímicas
PKA_CARBONIC = 6.1          # pKa del sistema CO2/HCO3- a temperatura corporal
SOLUBILITY_CO2 = 0.0307     # αCO2 en mEq/L/mmHg (Henry)
NORMAL_AG = 12.0            # AG normal sin corrección (mEq/L)
NORMAL_ALBUMIN_G_DL = 4.0   # Albúmina normal de referencia (g/dL)


def _henderson_hasselbalch(paco2_mmhg: float, hco3_meq_l: float) -> float:
    """pH por Henderson–Hasselbalch."""
    dissolved_co2 = SOLUBILITY_CO2 * paco2_mmhg
    if dissolved_co2 <= 0 or hco3_meq_l <= 0:
        raise ValueError("PaCO2 y HCO3 deben ser > 0 para H–H.")
    return PKA_CARBONIC + math.log10(hco3_meq_l / dissolved_co2)


def _anion_gap(na: float, cl: float, hco3: float) -> float:
    """AG = Na+ − (Cl− + HCO3−)  [mEq/L]."""
    return na - (cl + hco3)


def _ag_corrected(ag: float, albumin_g_dl: float) -> float:
    """AG corregido por albúmina: AG + 2.5 × (4.0 − Alb)."""
    return ag + 2.5 * (NORMAL_ALBUMIN_G_DL - albumin_g_dl)


def _winter_expected_paco2(hco3: float) -> tuple[float, float]:
    """
    Fórmula de Winter para compensación respiratoria en acidosis metabólica.
    PaCO2_esperada = 1.5 × HCO3 + 8 ± 2
    Retorna (lo, hi) del rango esperado.
    """
    center = 1.5 * hco3 + 8.0
    return center - 2.0, center + 2.0


def _sida(na: float, k: float, ca: float, mg: float, cl: float, lactate: float) -> float:
    """
    SID aparente Stewart (mEq/L):
    SIDa = (Na+ + K+ + Ca²+ + Mg²+) − (Cl− + lactato−)
    Nota: Ca y Mg en mEq/L (= mmol/L × valencia).
    """
    cations = na + k + ca + mg
    anions = cl + lactate
    return cations - anions


def _atot(albumin_g_dl: float, phosphate_mg_dl: float) -> float:
    """
    Atot ≈ 2.43 × Alb(g/dL) + 0.097 × Fosfato(mg/dL)
    Aproximación de Watson para ácidos débiles no volátiles.
    """
    return 2.43 * albumin_g_dl + 0.097 * phosphate_mg_dl


def _delta_delta(ag: float, hco3: float) -> float:
    """
    Delta-delta = (AG − 12) / (24 − HCO3)
    Indica trastorno mixto metabólico cuando está fuera de [1.0, 2.0].
    """
    denominator = 24.0 - hco3
    if abs(denominator) < 0.001:
        return float("nan")
    return (ag - NORMAL_AG) / denominator


def _primary_diagnosis(
    ph: float,
    paco2: float,
    hco3: float,
) -> tuple[str, str]:
    """
    Diagnóstico primario ácido–base con compensación esperada.

    Retorna:
        (primary_disorder, compensation_status)
    """
    # Clasificación primaria
    if ph < 7.35 and hco3 < 22:
        primary = "acidosis_metabolica"
    elif ph < 7.35 and paco2 > 45:
        primary = "acidosis_respiratoria"
    elif ph > 7.45 and hco3 > 26:
        primary = "alcalosis_metabolica"
    elif ph > 7.45 and paco2 < 35:
        primary = "alcalosis_respiratoria"
    elif 7.35 <= ph <= 7.45:
        primary = "ph_normal"
    else:
        primary = "trastorno_mixto_indeterminado"

    # Estado de compensación (solo para acidosis metabólica: Winter)
    compensation = "no_evaluada"
    if primary == "acidosis_metabolica":
        lo, hi = _winter_expected_paco2(hco3)
        if lo <= paco2 <= hi:
            compensation = "compensacion_respiratoria_adecuada"
        elif paco2 < lo:
            compensation = "hiperventilacion_adicional_alcalosis_respiratoria_concomitante"
        else:
            compensation = "hipoventilacion_acidosis_respiratoria_concomitante"
    elif primary == "acidosis_respiratoria":
        # Compensación renal esperada (aguda vs crónica)
        hco3_expected_acute = 24 + 0.1 * (paco2 - 40)
        hco3_expected_chronic = 24 + 0.35 * (paco2 - 40)
        if abs(hco3 - hco3_expected_acute) < 3:
            compensation = "compensacion_renal_aguda"
        elif abs(hco3 - hco3_expected_chronic) < 4:
            compensation = "compensacion_renal_cronica"
        else:
            compensation = "compensacion_renal_no_adecuada"

    return primary, compensation


def run_abg(
    ph: float,
    paco2: float,
    hco3: float,
    na: float,
    k: float,
    cl: float,
    albumin_g_dl: float = 4.0,
    phosphate_mg_dl: float = 3.5,
    ca_meq_l: float = 5.0,
    mg_meq_l: float = 1.8,
    lactate_meq_l: float = 1.0,
) -> ClinicalOutput:
    """
    Análisis gasométrico ácido–base completo.

    Args:
        ph:            pH arterial medido.
        paco2:         PaCO2 medido (mmHg).
        hco3:          HCO3− medido (mEq/L). Si se mide directamente del gas.
        na:            Na+ (mEq/L).
        k:             K+ (mEq/L).
        cl:            Cl− (mEq/L).
        albumin_g_dl:  Albúmina (g/dL). Default 4.0.
        phosphate_mg_dl: Fosfato (mg/dL). Default 3.5.
        ca_meq_l:      Ca²+ (mEq/L). Default 5.0.
        mg_meq_l:      Mg²+ (mEq/L). Default 1.8.
        lactate_meq_l: Lactato (mEq/L). Default 1.0.

    Returns:
        ClinicalOutput con todos los parámetros calculados y diagnóstico.
    """
    # Calcular pH por H–H para consistencia
    ph_calculated = _henderson_hasselbalch(paco2, hco3)
    ph_discrepancy = abs(ph - ph_calculated)
    consistency_ok = ph_discrepancy <= 0.05

    # AG y correcciones
    ag = _anion_gap(na, cl, hco3)
    ag_corr = _ag_corrected(ag, albumin_g_dl)
    dd = _delta_delta(ag, hco3)

    # Stewart
    sida = _sida(na, k, ca_meq_l, mg_meq_l, cl, lactate_meq_l)
    atot = _atot(albumin_g_dl, phosphate_mg_dl)

    # Winter
    winter_lo, winter_hi = _winter_expected_paco2(hco3)

    # Diagnóstico primario
    primary, compensation = _primary_diagnosis(ph, paco2, hco3)

    # Interpretación delta-delta
    if math.isnan(dd):
        dd_interp = "indeterminado"
    elif dd < 1.0:
        dd_interp = "AG_elevado_con_acidosis_metabolica_hipercloremia_concomitante"
    elif dd <= 2.0:
        dd_interp = "acidosis_metabolica_anion_gap_puro"
    else:
        dd_interp = "alcalosis_metabolica_concomitante_o_AG_elevado_previo"

    # AG elevado
    ag_elevated = ag_corr > 16.0

    # Etiqueta textual formal
    formal_label = primary
    if compensation not in ("no_evaluada",):
        formal_label += f" con {compensation}"

    explain = (
        f"pH medido: {ph:.3f} | pH H–H calculado: {ph_calculated:.3f} "
        f"({'consistente' if consistency_ok else 'INCONSISTENTE — verificar valores'})."
        f" Trastorno primario: {primary}. Compensación: {compensation}."
        f" AG: {ag:.1f} mEq/L, AGcorr: {ag_corr:.1f} mEq/L "
        f"({'elevado' if ag_elevated else 'normal'})."
        f" Delta-delta: {dd:.2f} → {dd_interp}."
        f" SIDa: {sida:.1f} mEq/L. Atot: {atot:.1f}."
        f" Winter PaCO2 esperada: [{winter_lo:.1f}, {winter_hi:.1f}] mmHg."
    )

    action = Action.OBSERVE  # Cálculo completo emitido; correlacionar con cuadro clínico

    return ClinicalOutput(
        result={
            "ph_measured": ph,
            "ph_calculated_hh": round(ph_calculated, 4),
            "ph_discrepancy": round(ph_discrepancy, 4),
            "consistency_ok": consistency_ok,
            "paco2": paco2,
            "hco3": hco3,
            "anion_gap": round(ag, 2),
            "anion_gap_corrected": round(ag_corr, 2),
            "ag_elevated": ag_elevated,
            "delta_delta": round(dd, 3) if not math.isnan(dd) else None,
            "delta_delta_interpretation": dd_interp,
            "winter_expected_paco2": {"lo": round(winter_lo, 1), "hi": round(winter_hi, 1)},
            "SIDa": round(sida, 2),
            "Atot": round(atot, 2),
            "primary_disorder": primary,
            "compensation": compensation,
            "formal_label": formal_label,
            "stewart_note": (
                "SIDa y Atot son aproximaciones cualitativas (Stewart completo "
                "requiere resolución numérica no implementada en este MVP)."
            ),
        },
        action=action,
        p=None,
        U=None,
        NB=None,
        units_ok=True,
        explain=explain,
        ci=None,
    )


def run(clinical_input_dict: dict[str, Any]) -> ClinicalOutput:
    """
    Interfaz estándar del módulo.

    Campos obligatorios en inputs:
      ph, paco2, hco3, na, k, cl

    Campos opcionales (con defaults fisiológicos):
      albumin_g_dl, phosphate_mg_dl, ca_meq_l, mg_meq_l, lactate_meq_l
    """
    inp = clinical_input_dict["inputs"]
    return run_abg(
        ph=float(inp["ph"]),
        paco2=float(inp["paco2"]),
        hco3=float(inp["hco3"]),
        na=float(inp["na"]),
        k=float(inp["k"]),
        cl=float(inp["cl"]),
        albumin_g_dl=float(inp.get("albumin_g_dl", 4.0)),
        phosphate_mg_dl=float(inp.get("phosphate_mg_dl", 3.5)),
        ca_meq_l=float(inp.get("ca_meq_l", 5.0)),
        mg_meq_l=float(inp.get("mg_meq_l", 1.8)),
        lactate_meq_l=float(inp.get("lactate_meq_l", 1.0)),
    )
