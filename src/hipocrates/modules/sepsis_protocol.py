"""
sepsis_protocol.py — Sepsis_Protocol_Engine  (Hipócrates SMNC-5+)

Motor computable de apoyo clínico para estratificación de sepsis.

Implementa:
  A. qSOFA (Quick SOFA): RR, SBP, alteración del estado mental
  B. SOFA parcial/operativo: solo los componentes con inputs presentes
     (renal-creatinina, hepático-bilirrubina, coagulación-plaquetas,
      respiratorio-PaO2/FiO2)
  C. Lactato sérico y flags de hipoperfusión
  D. MAP y soporte vasopresor
  E. Clasificación formal de severidad:
       low_suspicion | sepsis_probable | septic_shock_probable
  F. Bundle de acciones de alto nivel (sin antibióticos específicos ni dosis)
  G. Tiempo de revaloración recomendado

Criterios de referencia (adaptados para computabilidad parcial):
  Sepsis-3 (Singer 2016, JAMA): sepsis como disfunción orgánica potencialmente
  mortal causada por respuesta desregulada del huésped a infección.
  - Sepsis:         sospecha infección + SOFA ≥ 2 (o qSOFA ≥ 2 como screening)
  - Choque séptico: sepsis + vasopresores para mantener MAP ≥ 65
                    + lactato > 2 mmol/L sin hipovolemia

LIMITACIONES EXPLÍCITAS v1:
  - No accede a historial clínico ni EHR
  - No prescribe antibióticos ni dosis específicas
  - No incorpora respuesta a fluidos ni evaluación hemodinámica invasiva
  - No evalúa germen, antibiograma ni foco infeccioso específico
  - SOFA solo parcial: GCS y componente cardiovascular formal no calculados
  - La acción 'start_treatment' significa:
      "el output computacional apoya iniciar manejo clínico inmediato"
      y NO constituye una orden autónoma de tratamiento
  - La clasificación NO reemplaza criterio clínico directo

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from hipocrates.utils.types import Action, ClinicalOutput


# ─────────────────────────────────────────────────────────────────────────────
# Umbrales clínicos (referenciados explícitamente)
# ─────────────────────────────────────────────────────────────────────────────

# qSOFA
QSOFA_RR_THRESHOLD       = 22     # FR ≥ 22 rpm: 1 punto (Sepsis-3)
QSOFA_SBP_THRESHOLD      = 100    # PAS ≤ 100 mmHg: 1 punto (Sepsis-3)
QSOFA_POSITIVE_THRESHOLD = 2      # qSOFA ≥ 2 → screening positivo

# Lactato
LACTATE_ELEVATED_THRESHOLD        = 2.0   # ≥ 2.0 mmol/L: hipoperfusión tisular
LACTATE_MARKEDLY_ELEVATED         = 4.0   # ≥ 4.0 mmol/L: hipoperfusión grave
LACTATE_BORDERLINE_THRESHOLD      = 1.5   # ≥ 1.5 mmol/L: alerta moderada

# MAP (presión arterial media)
MAP_SHOCK_THRESHOLD       = 65.0  # < 65 mmHg: hipotensión compatible con choque
MAP_CONCERN_THRESHOLD     = 70.0  # < 70 mmHg: zona de alerta

# SOFA (componentes parciales)
SOFA_MEANINGFUL_THRESHOLD = 2     # SOFA parcial ≥ 2 sugiere disfunción orgánica

# Diuresis
URINE_LOW_THRESHOLD       = 0.5   # < 0.5 mL/kg/h: oliguria (alerta)


# ─────────────────────────────────────────────────────────────────────────────
# A. qSOFA
# ─────────────────────────────────────────────────────────────────────────────

def _compute_qsofa(
    rr: float,
    sbp: float,
    mental_status_altered: bool,
) -> tuple[int, list[str]]:
    """
    Calcula qSOFA (0–3 puntos).

    Criterio       Umbral          Puntos
    FR elevada     ≥ 22 rpm        1
    PAS baja       ≤ 100 mmHg      1
    Alteración EM  presente        1

    Returns:
        (score, componentes_positivos)
    """
    score = 0
    components: list[str] = []

    if rr >= QSOFA_RR_THRESHOLD:
        score += 1
        components.append(f"FR elevada (≥{QSOFA_RR_THRESHOLD} rpm): {rr:.1f} rpm")

    if sbp <= QSOFA_SBP_THRESHOLD:
        score += 1
        components.append(f"PAS baja (≤{QSOFA_SBP_THRESHOLD} mmHg): {sbp:.1f} mmHg")

    if mental_status_altered:
        score += 1
        components.append("Alteración del estado mental: presente")

    return score, components


# ─────────────────────────────────────────────────────────────────────────────
# B. SOFA parcial/operativo
# ─────────────────────────────────────────────────────────────────────────────

def _sofa_renal(creatinine_mg_dl: float) -> tuple[int, str]:
    """
    SOFA renal por creatinina sérica (mg/dL).
    Referencia: Tabla SOFA original (Vincent 1996 / Sepsis-3 2016).
    """
    if creatinine_mg_dl < 1.2:
        return 0, f"Creatinina {creatinine_mg_dl:.2f} mg/dL → renal SOFA 0"
    elif creatinine_mg_dl < 2.0:
        return 1, f"Creatinina {creatinine_mg_dl:.2f} mg/dL → renal SOFA 1"
    elif creatinine_mg_dl < 3.5:
        return 2, f"Creatinina {creatinine_mg_dl:.2f} mg/dL → renal SOFA 2"
    elif creatinine_mg_dl < 5.0:
        return 3, f"Creatinina {creatinine_mg_dl:.2f} mg/dL → renal SOFA 3"
    else:
        return 4, f"Creatinina {creatinine_mg_dl:.2f} mg/dL → renal SOFA 4"


def _sofa_hepatic(bilirubin_mg_dl: float) -> tuple[int, str]:
    """
    SOFA hepático por bilirrubina total (mg/dL).
    Referencia: Tabla SOFA (Vincent 1996 / Sepsis-3 2016).
    """
    if bilirubin_mg_dl < 1.2:
        return 0, f"Bilirrubina {bilirubin_mg_dl:.2f} mg/dL → hepático SOFA 0"
    elif bilirubin_mg_dl < 2.0:
        return 1, f"Bilirrubina {bilirubin_mg_dl:.2f} mg/dL → hepático SOFA 1"
    elif bilirubin_mg_dl < 6.0:
        return 2, f"Bilirrubina {bilirubin_mg_dl:.2f} mg/dL → hepático SOFA 2"
    elif bilirubin_mg_dl < 12.0:
        return 3, f"Bilirrubina {bilirubin_mg_dl:.2f} mg/dL → hepático SOFA 3"
    else:
        return 4, f"Bilirrubina {bilirubin_mg_dl:.2f} mg/dL → hepático SOFA 4"


def _sofa_coagulation(platelets_k_ul: float) -> tuple[int, str]:
    """
    SOFA coagulación por recuento de plaquetas (×10³/μL).
    Referencia: Tabla SOFA (Vincent 1996 / Sepsis-3 2016).
    """
    if platelets_k_ul >= 150:
        return 0, f"Plaquetas {platelets_k_ul:.0f} ×10³/μL → coagulación SOFA 0"
    elif platelets_k_ul >= 100:
        return 1, f"Plaquetas {platelets_k_ul:.0f} ×10³/μL → coagulación SOFA 1"
    elif platelets_k_ul >= 50:
        return 2, f"Plaquetas {platelets_k_ul:.0f} ×10³/μL → coagulación SOFA 2"
    elif platelets_k_ul >= 20:
        return 3, f"Plaquetas {platelets_k_ul:.0f} ×10³/μL → coagulación SOFA 3"
    else:
        return 4, f"Plaquetas {platelets_k_ul:.0f} ×10³/μL → coagulación SOFA 4"


def _sofa_respiratory(pao2_fio2: float, mechanical_ventilation: bool) -> tuple[int, str]:
    """
    SOFA respiratorio por índice PaO2/FiO2 (mmHg).
    Referencia: Tabla SOFA (Berlin 2012 / Sepsis-3 2016).
    Nota: puntuación 3 y 4 requieren ventilación mecánica según criterios ARDS.
    """
    if pao2_fio2 >= 400:
        return 0, f"PaO2/FiO2 {pao2_fio2:.0f} → respiratorio SOFA 0"
    elif pao2_fio2 >= 300:
        return 1, f"PaO2/FiO2 {pao2_fio2:.0f} → respiratorio SOFA 1"
    elif pao2_fio2 >= 200:
        return 2, f"PaO2/FiO2 {pao2_fio2:.0f} → respiratorio SOFA 2"
    elif pao2_fio2 >= 100 and mechanical_ventilation:
        return 3, f"PaO2/FiO2 {pao2_fio2:.0f} con VM → respiratorio SOFA 3"
    elif mechanical_ventilation:
        return 4, f"PaO2/FiO2 {pao2_fio2:.0f} con VM → respiratorio SOFA 4"
    else:
        # Sin VM no se puede puntuar 3-4 por criterio formal; se registra como 2
        return 2, (
            f"PaO2/FiO2 {pao2_fio2:.0f} sin VM documentada → respiratorio SOFA 2 "
            "(puntuación 3-4 requiere VM; se asigna 2 por precaución)"
        )


def _compute_sofa_partial(inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Calcula SOFA parcial con los componentes disponibles.

    Componentes evaluados:
      - Renal:         creatinine_mg_dL
      - Hepático:      bilirubin_mg_dL
      - Coagulación:   platelets_k_uL
      - Respiratorio:  pao2_fio2 (+ mechanical_ventilation)

    Componentes NO computados en v1 (datos no recogidos):
      - Cardiovascular SOFA formal (se evalúa MAP/vasopresor de forma independiente)
      - GCS/neurológico (no recogido como score numérico)

    Returns:
        dict con: components_available, partial_score, component_details, interpretation
    """
    component_scores: list[int] = []
    component_details: list[str] = []
    components_available: list[str] = []

    creatinine = inputs.get("creatinine_mg_dL")
    bilirubin  = inputs.get("bilirubin_mg_dL")
    platelets  = inputs.get("platelets_k_uL")
    pao2_fio2  = inputs.get("pao2_fio2")
    mech_vent  = bool(inputs.get("mechanical_ventilation", False))

    if creatinine is not None:
        s, d = _sofa_renal(float(creatinine))
        component_scores.append(s)
        component_details.append(d)
        components_available.append("renal")

    if bilirubin is not None:
        s, d = _sofa_hepatic(float(bilirubin))
        component_scores.append(s)
        component_details.append(d)
        components_available.append("hepatico")

    if platelets is not None:
        s, d = _sofa_coagulation(float(platelets))
        component_scores.append(s)
        component_details.append(d)
        components_available.append("coagulacion")

    if pao2_fio2 is not None:
        s, d = _sofa_respiratory(float(pao2_fio2), mech_vent)
        component_scores.append(s)
        component_details.append(d)
        components_available.append("respiratorio")

    partial_score = sum(component_scores)
    n = len(components_available)

    if n == 0:
        interpretation = (
            "No se proporcionaron datos suficientes para calcular ningún "
            "componente de SOFA. La clasificación de severidad se basa en "
            "qSOFA, lactato y MAP."
        )
    elif partial_score >= SOFA_MEANINGFUL_THRESHOLD:
        interpretation = (
            f"SOFA parcial {partial_score} puntos ({n} componente(s) evaluado(s): "
            f"{', '.join(components_available)}). Score ≥ 2 sugiere disfunción "
            "orgánica. SOFA completo requeriría GCS y componente cardiovascular formal."
        )
    else:
        interpretation = (
            f"SOFA parcial {partial_score} puntos ({n} componente(s) evaluado(s): "
            f"{', '.join(components_available)}). Score < 2 con datos disponibles. "
            "No excluye disfunción en componentes no evaluados."
        )

    return {
        "sofa_components_available": components_available,
        "sofa_n_components": n,
        "sofa_partial_score": partial_score,
        "sofa_component_details": component_details,
        "sofa_interpretation": interpretation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# C. Lactato, MAP y perfusión
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate_lactate(lactate_mmol_l: float) -> dict[str, Any]:
    """
    Clasifica el lactato sérico y genera flags clínicos.

    Umbrales (mmol/L):
      < 1.5:  normal / sin alerta
      1.5–2.0: zona limítrofe / vigilar
      ≥ 2.0:  elevado — hipoperfusión tisular compatible
      ≥ 4.0:  marcadamente elevado — hipoperfusión grave
    """
    flag = False
    level = "normal"
    detail = ""

    if lactate_mmol_l >= LACTATE_MARKEDLY_ELEVATED:
        flag = True
        level = "markedly_elevated"
        detail = (
            f"Lactato {lactate_mmol_l:.1f} mmol/L (≥{LACTATE_MARKEDLY_ELEVATED}): "
            "hipoperfusión tisular grave. Criterio de choque metabólico."
        )
    elif lactate_mmol_l >= LACTATE_ELEVATED_THRESHOLD:
        flag = True
        level = "elevated"
        detail = (
            f"Lactato {lactate_mmol_l:.1f} mmol/L (≥{LACTATE_ELEVATED_THRESHOLD}): "
            "elevado. Compatible con hipoperfusión tisular. Criterio diagnóstico Sepsis-3."
        )
    elif lactate_mmol_l >= LACTATE_BORDERLINE_THRESHOLD:
        flag = False
        level = "borderline"
        detail = (
            f"Lactato {lactate_mmol_l:.1f} mmol/L (≥{LACTATE_BORDERLINE_THRESHOLD}): "
            "zona de alerta. Vigilar tendencia y contexto clínico."
        )
    else:
        flag = False
        level = "normal"
        detail = (
            f"Lactato {lactate_mmol_l:.1f} mmol/L: dentro del rango de referencia."
        )

    return {
        "lactate_flag": flag,
        "lactate_level": level,
        "lactate_detail": detail,
    }


def _evaluate_map(map_mmhg: float) -> dict[str, Any]:
    """
    Evalúa la presión arterial media (MAP) en mmHg.

    Umbrales:
      ≥ 70:  adecuada para mayoría de contextos
      65–69: límite inferior de perfusión aceptable
      < 65:  hipotensión — criterio hemodinámico de choque
    """
    if map_mmhg < MAP_SHOCK_THRESHOLD:
        flag = True
        detail = (
            f"MAP {map_mmhg:.1f} mmHg (<{MAP_SHOCK_THRESHOLD}): "
            "hipotensión arterial. Criterio hemodinámico de choque séptico (Sepsis-3)."
        )
    elif map_mmhg < MAP_CONCERN_THRESHOLD:
        flag = True
        detail = (
            f"MAP {map_mmhg:.1f} mmHg (<{MAP_CONCERN_THRESHOLD}): "
            "zona de alerta. Monitorización estrecha de perfusión."
        )
    else:
        flag = False
        detail = (
            f"MAP {map_mmhg:.1f} mmHg: dentro de rango aceptable de perfusión (≥{MAP_CONCERN_THRESHOLD} mmHg)."
        )

    return {"map_flag": flag, "map_detail": detail}


def _evaluate_urine_output(urine_ml_kg_h: Optional[float]) -> dict[str, Any]:
    """
    Evalúa diuresis horaria si está disponible.
    Oliguria: < 0.5 mL/kg/h.
    """
    if urine_ml_kg_h is None:
        return {
            "urine_output_flag": False,
            "urine_output_detail": "Diuresis no proporcionada (campo opcional).",
        }

    if urine_ml_kg_h < URINE_LOW_THRESHOLD:
        return {
            "urine_output_flag": True,
            "urine_output_detail": (
                f"Diuresis {urine_ml_kg_h:.2f} mL/kg/h (<{URINE_LOW_THRESHOLD}): "
                "oliguria — señal de hipoperfusión renal."
            ),
        }
    return {
        "urine_output_flag": False,
        "urine_output_detail": (
            f"Diuresis {urine_ml_kg_h:.2f} mL/kg/h: sin criterio de oliguria."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# D. Clasificación de severidad
# ─────────────────────────────────────────────────────────────────────────────

def _classify_severity(
    suspected_infection: bool,
    qsofa_score: int,
    sofa_partial_score: int,
    lactate_flag: bool,
    lactate_level: str,
    lactate_mmol_l: float,
    map_flag: bool,
    map_mmhg: float,
    vasopressor: bool,
    urine_output_flag: bool,
) -> tuple[str, str, list[str]]:
    """
    Clasifica la severidad en: low_suspicion | sepsis_probable | septic_shock_probable.

    Lógica explícita y trazable:

    1. Sin sospecha infecciosa → low_suspicion
       (criterio: sospecha infecciosa es condición necesaria por definición Sepsis-3)

    2. Con sospecha infecciosa:
       a. septic_shock_probable:
          lactato ≥ 2.0 mmol/L  AND  (MAP < 65 mmHg  OR  vasopresor activo)
          → hipotensión/vasopresores persistentes + hipoperfusión metabólica

       b. sepsis_probable (evidencia sólida):
          qSOFA ≥ 2  OR  SOFA_parcial ≥ 2  OR  lactato ≥ 2.0 mmol/L

       c. sepsis_probable (señales de alerta):
          qSOFA = 1  AND  (lactato ≥ 1.5 mmol/L  OR  oliguria  OR  MAP < 70)

       d. low_suspicion:
          Sospecha infecciosa presente pero sin señales de disfunción orgánica
          con los datos disponibles. Monitorización y revaloración.

    Returns:
        (severity_class, razon_clasificacion, criterios_positivos_lista)
    """
    criteria_met: list[str] = []

    if not suspected_infection:
        return (
            "low_suspicion",
            "No hay sospecha infecciosa documentada. La sospecha de infección "
            "es condición necesaria para el diagnóstico de sepsis (Sepsis-3). "
            "Se recomienda monitorización clínica y revaloración periódica.",
            [],
        )

    # Identificar criterios positivos
    if qsofa_score >= QSOFA_POSITIVE_THRESHOLD:
        criteria_met.append(f"qSOFA ≥ 2 ({qsofa_score} puntos)")
    elif qsofa_score == 1:
        criteria_met.append(f"qSOFA = 1 (señal de alerta, no umbral diagnóstico)")

    if sofa_partial_score >= SOFA_MEANINGFUL_THRESHOLD:
        criteria_met.append(f"SOFA parcial ≥ 2 ({sofa_partial_score} puntos)")

    if lactate_level == "markedly_elevated":
        criteria_met.append(f"Lactato marcadamente elevado (≥{LACTATE_MARKEDLY_ELEVATED} mmol/L)")
    elif lactate_flag:
        criteria_met.append(f"Lactato elevado (≥{LACTATE_ELEVATED_THRESHOLD} mmol/L)")
    elif lactate_level == "borderline":
        criteria_met.append(f"Lactato en zona limítrofe (≥{LACTATE_BORDERLINE_THRESHOLD} mmol/L)")

    if map_mmhg < MAP_SHOCK_THRESHOLD:
        criteria_met.append(f"MAP < {MAP_SHOCK_THRESHOLD} mmHg ({map_mmhg:.1f})")
    elif map_mmhg < MAP_CONCERN_THRESHOLD:
        criteria_met.append(f"MAP en zona de alerta ({map_mmhg:.1f} mmHg)")

    if vasopressor:
        criteria_met.append("Soporte vasopresor activo")

    if urine_output_flag:
        criteria_met.append("Oliguria presente")

    # ── Clasificación (orden: más grave primero) ──────────────────────────────

    # Septic shock: lactato elevado + hipotensión/vasopresor
    is_shock_hemodynamic = (map_mmhg < MAP_SHOCK_THRESHOLD or vasopressor)
    is_shock_metabolic   = (lactate_mmol_l >= LACTATE_ELEVATED_THRESHOLD)

    if is_shock_hemodynamic and is_shock_metabolic:
        return (
            "septic_shock_probable",
            (
                f"Sospecha infecciosa + lactato elevado ({lactate_mmol_l:.1f} mmol/L ≥ "
                f"{LACTATE_ELEVATED_THRESHOLD}) + criterio hemodinámico "
                f"({'MAP ' + str(round(map_mmhg,1)) + ' mmHg < ' + str(MAP_SHOCK_THRESHOLD) if map_mmhg < MAP_SHOCK_THRESHOLD else ''}"
                f"{'/ ' if map_mmhg < MAP_SHOCK_THRESHOLD and vasopressor else ''}"
                f"{'vasopresor activo' if vasopressor else ''}). "
                "Patrón compatible con choque séptico según criterios Sepsis-3 adaptados."
            ),
            criteria_met,
        )

    # Sepsis probable — evidencia sólida
    if (qsofa_score >= QSOFA_POSITIVE_THRESHOLD
            or sofa_partial_score >= SOFA_MEANINGFUL_THRESHOLD
            or lactate_mmol_l >= LACTATE_ELEVATED_THRESHOLD):
        return (
            "sepsis_probable",
            (
                "Sospecha infecciosa + disfunción orgánica probable: "
                + " | ".join(
                    c for c in [
                        f"qSOFA {qsofa_score}" if qsofa_score >= 2 else "",
                        f"SOFA parcial {sofa_partial_score}" if sofa_partial_score >= 2 else "",
                        f"lactato {lactate_mmol_l:.1f} mmol/L" if lactate_mmol_l >= LACTATE_ELEVATED_THRESHOLD else "",
                    ] if c
                )
                + ". Patrón compatible con sepsis según criterios Sepsis-3 adaptados."
            ),
            criteria_met,
        )

    # Sepsis probable — señales de alerta (umbral menor pero contexto preocupante)
    has_alert_signals = (
        (qsofa_score >= 1 and (lactate_level in ("borderline", "elevated", "markedly_elevated")))
        or (qsofa_score >= 1 and urine_output_flag)
        or (qsofa_score >= 1 and map_mmhg < MAP_CONCERN_THRESHOLD)
    )
    if has_alert_signals:
        return (
            "sepsis_probable",
            (
                "Sospecha infecciosa + señales de alerta combinadas (qSOFA=1 con "
                "otros indicadores: lactato limítrofe y/o oliguria y/o MAP < 70). "
                "Disfunción orgánica no claramente establecida con datos disponibles. "
                "Se recomienda vigilancia estricta y obtención de datos adicionales."
            ),
            criteria_met,
        )

    # Low suspicion con infección sospechada pero sin señales suficientes
    return (
        "low_suspicion",
        (
            "Sospecha infecciosa presente, pero sin señales de disfunción orgánica "
            "suficientes con los datos disponibles (qSOFA < 2, SOFA parcial < 2, "
            "lactato < 2.0 mmol/L, MAP adecuada, sin vasopresor). "
            "No excluye sepsis si los datos disponibles son incompletos. "
            "Monitorización clínica y revaloración periódica."
        ),
        criteria_met,
    )


# ─────────────────────────────────────────────────────────────────────────────
# E. Bundle de acciones de alto nivel
# ─────────────────────────────────────────────────────────────────────────────

def _build_bundle(
    severity_class: str,
    action: str,
    lactate_flag: bool,
    vasopressor: bool,
    has_sofa_components: bool,
    urine_output_flag: bool,
    pao2_fio2_present: bool,
    mechanical_ventilation: bool,
) -> list[str]:
    """
    Genera bundle de acciones clínicas de alto nivel alineado con severity_class Y action.

    El nivel de intervención recomendado corresponde a la acción computacional,
    no solo a la clasificación de severidad:

      - sepsis_probable + obtain_test  → bundle de evaluación y confirmación
      - sepsis_probable + start_treatment → bundle intervencionista de sepsis probable
      - septic_shock_probable + start_treatment → bundle urgente

    NO prescribe antibióticos específicos ni dosis.
    Las acciones son orientativas y requieren valoración clínica directa.
    """
    bundle: list[str] = []

    if severity_class == "low_suspicion":
        bundle += [
            "Monitorización clínica y de signos vitales.",
            "Revalorar sospecha infecciosa con anamnesis y exploración.",
            "Considerar fuente potencial de infección.",
            "Reevaluar en 60 minutos o antes si deterioro.",
        ]

    elif severity_class == "sepsis_probable":
        if action == Action.OBTAIN_TEST:
            # Bundle de evaluación y confirmación: aún no hay evidencia suficiente
            # para recomendar tratamiento; el objetivo es obtener datos que aclaren.
            bundle += [
                "Repetir lactato sérico y monitorizar tendencia.",
                "Completar analítica para SOFA parcial/completo: creatinina, bilirrubina, "
                "plaquetas, hemograma, coagulación, gasometría arterial (PaO2/FiO2).",
                "Revalorar perfusión periférica y signos vitales.",
                "Identificar y caracterizar foco infeccioso probable.",
                "Monitorización estrecha con signos vitales cada 15-30 minutos.",
                "Obtener acceso venoso periférico si no disponible.",
            ]
            if urine_output_flag:
                bundle.append(
                    "Vigilar diuresis horaria; considerar sondaje para control estricto."
                )
            bundle.append(
                "Reevaluar la decisión de tratamiento en el próximo control "
                "(reclasificar si deterioro o nuevos datos confirman disfunción orgánica)."
            )
        else:
            # action == START_TREATMENT: evidencia sólida de disfunción orgánica
            bundle += [
                "Obtener hemocultivos (mínimo 2 series, diferentes sitios) antes de iniciar antibióticos.",
            ]
            if not lactate_flag:
                bundle.append("Determinar lactato sérico si no disponible.")
            else:
                bundle.append("Repetir lactato sérico en 2 horas para evaluar tendencia.")
            bundle += [
                "Iniciar reanimación con líquidos IV (cristaloide isotónico balanceado), guiada por respuesta clínica.",
                "Valorar inicio de antibioterapia empírica de amplio espectro (según foco y contexto local).",
                "Monitorización horaria de diuresis.",
                "Obtener acceso venoso periférico de calibre adecuado.",
            ]
            if not has_sofa_components:
                bundle.append(
                    "Solicitar analítica completa: creatinina, bilirrubina, plaquetas, "
                    "hemograma, coagulación, gasometría arterial (PaO2/FiO2) para SOFA completo."
                )
            if urine_output_flag:
                bundle.append("Valorar sondaje urinario para control estricto de diuresis horaria.")
            bundle.append("Reevaluar perfusión y respuesta clínica en 30 minutos.")

    elif severity_class == "septic_shock_probable":
        bundle += [
            "URGENTE: Obtener hemocultivos inmediatamente (no demorar antibióticos).",
            "URGENTE: Iniciar antibioterapia empírica de amplio espectro en los primeros 60 minutos.",
            "Reanimación agresiva con líquidos: cristaloide isotónico 30 mL/kg en primeras 3 horas "
            "(ajustar a respuesta hemodinámica y tolerancia).",
        ]
        if not lactate_flag:
            bundle.append("Determinar lactato sérico URGENTE.")
        else:
            bundle.append(
                "Repetir lactato sérico en 2 horas para monitorizar aclaramiento "
                "(objetivo: reducción ≥ 10% o < 2 mmol/L)."
            )
        if not vasopressor:
            bundle.append(
                "Valorar inicio de vasopresores (norepinefrina de primera línea) "
                "si hipotensión persiste tras reanimación con líquidos."
            )
        else:
            bundle.append(
                "Vigilar dosis y respuesta a vasopresores activos. "
                "Considerar corticoterapia si dosis altas con respuesta insuficiente."
            )
        bundle += [
            "Valorar ingreso en UCI / área de monitorización intensiva.",
            "Considerar acceso arterial y venoso central para monitorización hemodinámica.",
            "Monitorización horaria de diuresis (objetivo > 0.5 mL/kg/h).",
            "Solicitar analítica completa urgente: hemograma, bioquímica, coagulación, "
            "gasometría arterial, lactato.",
        ]
        if mechanical_ventilation:
            bundle.append(
                "Ventilación mecánica activa documentada: "
                "ajustar parámetros según estado hemodinámico y oxigenación."
            )
        if pao2_fio2_present:
            bundle.append(
                "Vigilar índice PaO2/FiO2 y signos de ARDS."
            )
        bundle.append("Reevaluar perfusión y respuesta hemodinámica en 15 minutos.")

    return bundle


# ─────────────────────────────────────────────────────────────────────────────
# F. Tiempo de revaloración
# ─────────────────────────────────────────────────────────────────────────────

def _recheck_time(severity_class: str, lactate_level: str) -> int:
    """
    Recomienda tiempo de revaloración en minutos según severidad.

    low_suspicion:        60 min
    sepsis_probable:      30 min
    septic_shock_probable: 15 min

    El lactato marcadamente elevado acorta el tiempo incluso en sepsis_probable.
    """
    if severity_class == "septic_shock_probable":
        return 15
    if severity_class == "sepsis_probable":
        if lactate_level == "markedly_elevated":
            return 15
        return 30
    return 60


# ─────────────────────────────────────────────────────────────────────────────
# Mappings de presentación (uso local dentro del módulo — solo para explain)
# No acoplar con Streamlit ni con ui_helpers.
# Los valores internos del result NO se alteran.
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_LABEL: dict[str, str] = {
    "low_suspicion":         "Sospecha baja de sepsis",
    "sepsis_probable":       "Sepsis probable",
    "septic_shock_probable": "Choque séptico probable",
}

_LACTATE_LABEL: dict[str, str] = {
    "normal":            "normal",
    "borderline":        "zona limítrofe (≥ 1.5 mmol/L)",
    "elevated":          "elevado (≥ 2.0 mmol/L)",
    "markedly_elevated": "marcadamente elevado (≥ 4.0 mmol/L)",
}


# ─────────────────────────────────────────────────────────────────────────────
# G. Acción canónica
# ─────────────────────────────────────────────────────────────────────────────

def _determine_action(
    severity_class: str,
    qsofa_score: int,
    sofa_partial_score: int,
    lactate_flag: bool,
    map_flag: bool,
    urine_output_flag: bool,
    vasopressor_flag: bool,
    has_sofa_components: bool,
) -> tuple[str, str]:
    """
    Determina la acción canónica según el contrato SMNC-5+.

    Monitorizar:                Sospecha baja, sin señales de disfunción.
    Solicitar información:      Sospecha infecciosa pero datos insuficientes.
    Iniciar manejo clínico:     Output apoya intervención inmediata de alto nivel.

    NOTA: 'start_treatment' (Iniciar manejo clínico) en este módulo NO es
    una orden autónoma. El bundle sugiere acciones de alto nivel; la decisión
    final siempre recae en el clínico responsable.

    ── Regla para sepsis_probable (v1.1, más prudente) ─────────────────────────
    start_treatment solo si existe evidencia clínico-computable sólida:
      - qSOFA >= 2, O
      - SOFA parcial >= 2, O
      - lactato elevado (>= 2.0) CON al menos un signo adicional de disfunción/
        hipoperfusión: MAP baja, oliguria, vasopresor o qSOFA >= 1.

    Motivo del cambio:
    El lactato aislado >= 2.0 mmol/L sin ningún otro dato de disfunción
    orgánica computable (qSOFA 0, MAP normal, sin oliguria, sin vasopresor)
    no es suficiente por sí solo para escalar a acción inmediata desde este
    módulo. Puede reflejar lactato de esfuerzo, alcalosis, hiperventiación
    u otras causas no sépticas. En ese caso se devuelve obtain_test para
    completar la evaluación antes de escalar el manejo.
    """
    if severity_class == "septic_shock_probable":
        return (
            Action.START_TREATMENT,
            "El output computacional apoya iniciar manejo clínico inmediato compatible "
            "con choque séptico probable (bundle de alto nivel). "
            "No es una orden autónoma — requiere valoración clínica directa.",
        )

    if severity_class == "sepsis_probable":
        # Evidencia sólida: qSOFA >= 2 o SOFA >= 2 → start_treatment
        if qsofa_score >= QSOFA_POSITIVE_THRESHOLD or sofa_partial_score >= SOFA_MEANINGFUL_THRESHOLD:
            return (
                Action.START_TREATMENT,
                "El output computacional apoya iniciar manejo clínico inmediato "
                "compatible con sepsis probable (qSOFA ≥ 2 o SOFA parcial ≥ 2). "
                "No es una orden autónoma — requiere valoración clínica directa.",
            )

        # Lactato elevado + al menos un signo adicional computable → start_treatment
        lactate_with_support = lactate_flag and (
            map_flag or urine_output_flag or vasopressor_flag or qsofa_score >= 1
        )
        if lactate_with_support:
            return (
                Action.START_TREATMENT,
                "El output computacional apoya iniciar manejo clínico inmediato "
                "compatible con sepsis probable (lactato elevado con signo adicional "
                "de disfunción/hipoperfusión). "
                "No es una orden autónoma — requiere valoración clínica directa.",
            )

        # Lactato elevado aislado (sin otros datos de disfunción computable) → obtain_test
        # o cualquier otro patrón de alerta insuficiente
        return (
            Action.OBTAIN_TEST,
            "Sospecha de sepsis con señales de alerta, pero evidencia insuficiente "
            "para escalar el manejo desde este módulo. "
            "Se recomienda completar la evaluación: lactato seriado, analítica "
            "(SOFA completo), reevaluar signos vitales y disfunción orgánica.",
        )

    # low_suspicion
    return (
        Action.OBSERVE,
        "Sin señales de disfunción orgánica suficientes con los datos disponibles. "
        "Monitorización clínica activa y revaloración periódica.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Limitaciones del módulo (declaradas explícitamente en la salida)
# ─────────────────────────────────────────────────────────────────────────────

_LIMITATIONS_V1: list[str] = [
    "SOFA parcial: no se calcula componente GCS (no recogido como score numérico) "
    "ni cardiovascular formal (MAP/vasopresor se evalúan de forma independiente).",
    "No incorpora respuesta a fluidos ni evaluación hemodinámica invasiva.",
    "No prescribe antibióticos específicos, dosis ni ajuste por función renal/hepática.",
    "No evalúa foco infeccioso específico, germen ni resistencias.",
    "La clasificación se basa en los inputs proporcionados; inputs ausentes implican "
    "incertidumbre diagnóstica no cuantificada.",
    "'start_treatment' significa: el output computacional apoya iniciar manejo "
    "clínico inmediato. NO es una orden autónoma de tratamiento.",
]


# ─────────────────────────────────────────────────────────────────────────────
# Motor principal
# ─────────────────────────────────────────────────────────────────────────────

def compute_sepsis(
    patient_id: str,
    suspected_infection: bool,
    rr: float,
    sbp: float,
    mental_status_altered: bool,
    map_mmhg: float,
    lactate_mmol_l: float,
    vasopressor: bool,
    urine_output_ml_kg_h: Optional[float] = None,
    creatinine_mg_dl: Optional[float] = None,
    bilirubin_mg_dl: Optional[float] = None,
    platelets_k_ul: Optional[float] = None,
    pao2_fio2: Optional[float] = None,
    mechanical_ventilation: bool = False,
) -> ClinicalOutput:
    """
    Motor de cálculo principal del Sepsis_Protocol_Engine.

    Parámetros requeridos:
        patient_id             Identificador del paciente
        suspected_infection    Bool: ¿hay sospecha clínica de infección?
        rr                     Frecuencia respiratoria (rpm)
        sbp                    Presión arterial sistólica (mmHg)
        mental_status_altered  Bool: ¿alteración del estado mental?
        map_mmhg               Presión arterial media (mmHg)
        lactate_mmol_l         Lactato sérico (mmol/L)
        vasopressor            Bool: ¿hay soporte vasopresor activo?

    Parámetros opcionales (mejoran SOFA parcial y flags):
        urine_output_ml_kg_h   Diuresis (mL/kg/h)
        creatinine_mg_dl       Creatinina sérica (mg/dL) — SOFA renal
        bilirubin_mg_dl        Bilirrubina total (mg/dL) — SOFA hepático
        platelets_k_ul         Plaquetas (×10³/μL) — SOFA coagulación
        pao2_fio2              Índice PaO2/FiO2 (mmHg) — SOFA respiratorio
        mechanical_ventilation  Bool: ¿ventilación mecánica activa?

    Returns:
        ClinicalOutput con salida homogénea SMNC-5+
    """
    warnings: list[str] = []

    # ── qSOFA ─────────────────────────────────────────────────────────────────
    qsofa_score, qsofa_components = _compute_qsofa(rr, sbp, mental_status_altered)
    qsofa_positive = (qsofa_score >= QSOFA_POSITIVE_THRESHOLD)

    qsofa_interpretation = (
        f"qSOFA {qsofa_score}/3"
        + (" (≥ 2: screening positivo para disfunción orgánica)" if qsofa_positive
           else " (< 2: screening no positivo, no excluye sepsis)")
    )

    # ── SOFA parcial ─────────────────────────────────────────────────────────
    sofa_inputs = {
        "creatinine_mg_dL": creatinine_mg_dl,
        "bilirubin_mg_dL": bilirubin_mg_dl,
        "platelets_k_uL": platelets_k_ul,
        "pao2_fio2": pao2_fio2,
        "mechanical_ventilation": mechanical_ventilation,
    }
    sofa_result = _compute_sofa_partial(sofa_inputs)
    sofa_partial_score = sofa_result["sofa_partial_score"]
    has_sofa_components = sofa_result["sofa_n_components"] > 0

    if not has_sofa_components:
        warnings.append(
            "No se proporcionaron datos para ningún componente de SOFA "
            "(creatinina, bilirrubina, plaquetas, PaO2/FiO2). "
            "La clasificación depende exclusivamente de qSOFA, lactato y MAP."
        )

    # ── Lactato ───────────────────────────────────────────────────────────────
    lactate_eval = _evaluate_lactate(lactate_mmol_l)
    lactate_flag  = lactate_eval["lactate_flag"]
    lactate_level = lactate_eval["lactate_level"]

    # ── MAP ───────────────────────────────────────────────────────────────────
    map_eval = _evaluate_map(map_mmhg)
    map_flag = map_eval["map_flag"]

    # ── Vasopresor ────────────────────────────────────────────────────────────
    vasopressor_flag = vasopressor

    # ── Diuresis ──────────────────────────────────────────────────────────────
    urine_eval = _evaluate_urine_output(urine_output_ml_kg_h)
    urine_output_flag = urine_eval["urine_output_flag"]

    # ── Hipoperfusión global ──────────────────────────────────────────────────
    hypoperfusion_flag = (
        lactate_flag
        and (map_flag or vasopressor_flag or urine_output_flag)
    )

    # ── Clasificación de severidad ────────────────────────────────────────────
    severity_class, severity_reason, criteria_positive = _classify_severity(
        suspected_infection=suspected_infection,
        qsofa_score=qsofa_score,
        sofa_partial_score=sofa_partial_score,
        lactate_flag=lactate_flag,
        lactate_level=lactate_level,
        lactate_mmol_l=lactate_mmol_l,
        map_flag=map_flag,
        map_mmhg=map_mmhg,
        vasopressor=vasopressor,
        urine_output_flag=urine_output_flag,
    )

    # ── Acción canónica (antes del bundle para que éste pueda alinearse) ────────
    action, action_reason = _determine_action(
        severity_class=severity_class,
        qsofa_score=qsofa_score,
        sofa_partial_score=sofa_partial_score,
        lactate_flag=lactate_flag,
        map_flag=map_flag,
        urine_output_flag=urine_output_flag,
        vasopressor_flag=vasopressor_flag,
        has_sofa_components=has_sofa_components,
    )

    # ── Bundle alineado con la action computada ───────────────────────────────
    bundle_actions = _build_bundle(
        severity_class=severity_class,
        action=action,
        lactate_flag=lactate_flag,
        vasopressor=vasopressor,
        has_sofa_components=has_sofa_components,
        urine_output_flag=urine_output_flag,
        pao2_fio2_present=(pao2_fio2 is not None),
        mechanical_ventilation=mechanical_ventilation,
    )

    # ── Tiempo de revaloración ────────────────────────────────────────────────
    recheck_time_minutes = _recheck_time(severity_class, lactate_level)

    # ── Texto de razonamiento (legible — sin strings internos crudos) ──────────
    # Los valores internos (severity_class, lactate_level, etc.) se conservan en
    # result. El texto explain usa etiquetas clínicas visibles para legibilidad.
    explain_parts = [
        f"Paciente {patient_id}.",
        f"Sospecha infecciosa: {'SÍ' if suspected_infection else 'NO'}.",
        f"qSOFA: {qsofa_score}/3 {'(positivo)' if qsofa_positive else '(negativo)'}.",
        f"SOFA parcial: {sofa_partial_score} pts ({sofa_result['sofa_n_components']} componente(s)).",
        f"Lactato: {lactate_mmol_l:.1f} mmol/L — {_LACTATE_LABEL.get(lactate_level, lactate_level)}.",
        f"MAP: {map_mmhg:.1f} mmHg {'(BAJA)' if map_flag else '(OK)'}.",
        f"Vasopresor: {'SÍ' if vasopressor else 'NO'}.",
        f"Clasificación: {_SEVERITY_LABEL.get(severity_class, severity_class)}.",
        f"Razón: {severity_reason}",
        f"Decisión del sistema: {action_reason}",
    ]
    # Nota discriminante: cuando la clase es sepsis_probable pero la evidencia
    # de disfunción orgánica aún no es suficiente para recomendar tratamiento,
    # se indica explícitamente que el bundle es de confirmación, no de inicio.
    if severity_class == "sepsis_probable" and action == Action.OBTAIN_TEST:
        explain_parts.append(
            "Nota: el bundle recomendado es de evaluación y confirmación "
            "(señales de disfunción orgánica insuficientes para tratamiento autónomo)."
        )
    if warnings:
        explain_parts.append("Advertencias: " + " | ".join(warnings))

    explain = " ".join(explain_parts)

    # ── Resultado estructurado ────────────────────────────────────────────────
    result = {
        # Inputs clave (para trazabilidad)
        "suspected_infection": suspected_infection,
        "rr_rpm": rr,
        "sbp_mmhg": sbp,
        "mental_status_altered": mental_status_altered,
        "map_mmhg": map_mmhg,
        "lactate_mmol_l": lactate_mmol_l,
        "vasopressor": vasopressor,
        # qSOFA
        "qsofa_score": qsofa_score,
        "qsofa_positive": qsofa_positive,
        "qsofa_components": qsofa_components,
        "qsofa_interpretation": qsofa_interpretation,
        # SOFA parcial
        "sofa_components_available": sofa_result["sofa_components_available"],
        "sofa_n_components_evaluated": sofa_result["sofa_n_components"],
        "sofa_partial_score": sofa_partial_score,
        "sofa_component_details": sofa_result["sofa_component_details"],
        "sofa_interpretation": sofa_result["sofa_interpretation"],
        # Lactato
        "lactate_flag": lactate_flag,
        "lactate_level": lactate_level,
        "lactate_detail": lactate_eval["lactate_detail"],
        # MAP
        "map_flag": map_flag,
        "map_detail": map_eval["map_detail"],
        # Vasopresor y diuresis
        "vasopressor_flag": vasopressor_flag,
        "urine_output_flag": urine_output_flag,
        "urine_output_detail": urine_eval["urine_output_detail"],
        # Hipoperfusión global
        "hypoperfusion_flag": hypoperfusion_flag,
        # Criterios que activaron la clasificación
        "criteria_positive": criteria_positive,
        # Clasificación final
        "severity_class": severity_class,
        "severity_reason": severity_reason,
        # Bundle y revaloración
        "bundle_actions": bundle_actions,
        "recheck_time_minutes": recheck_time_minutes,
        # Meta
        "warnings": warnings,
        "limitations": _LIMITATIONS_V1,
    }

    return ClinicalOutput(
        result=result,
        action=action,
        p=None,     # No hay probabilidad posterior (no es módulo Bayesiano)
        U=None,     # No hay utilidad esperada calculada
        NB=None,    # No hay NB (no es DCA)
        units_ok=True,  # El gate se ejecutó antes; aquí se asume ok
        explain=explain,
        ci=None,    # No hay IC en v1
    )


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada del orquestador (patrón del sistema)
# ─────────────────────────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> ClinicalOutput:
    """
    Punto de entrada del orquestador para el módulo sepsis_protocol.

    Extrae los inputs del payload validado y llama a compute_sepsis().
    El payload ya ha pasado por SchemaValidation y UnitsGate antes de llegar aquí.

    Args:
        payload: Dict con claves patient_id, module, inputs, constraints, version

    Returns:
        ClinicalOutput homogéneo
    """
    patient_id = payload["patient_id"]
    inputs = payload["inputs"]

    return compute_sepsis(
        patient_id=patient_id,
        suspected_infection=bool(inputs["suspected_infection"]),
        rr=float(inputs["rr"]),
        sbp=float(inputs["sbp"]),
        mental_status_altered=bool(inputs["mental_status_altered"]),
        map_mmhg=float(inputs["map_mmHg"]),
        lactate_mmol_l=float(inputs["lactate_mmol_L"]),
        vasopressor=bool(inputs["vasopressor"]),
        # Opcionales
        urine_output_ml_kg_h=(
            float(inputs["urine_output_ml_kg_h"])
            if inputs.get("urine_output_ml_kg_h") is not None
            else None
        ),
        creatinine_mg_dl=(
            float(inputs["creatinine_mg_dL"])
            if inputs.get("creatinine_mg_dL") is not None
            else None
        ),
        bilirubin_mg_dl=(
            float(inputs["bilirubin_mg_dL"])
            if inputs.get("bilirubin_mg_dL") is not None
            else None
        ),
        platelets_k_ul=(
            float(inputs["platelets_k_uL"])
            if inputs.get("platelets_k_uL") is not None
            else None
        ),
        pao2_fio2=(
            float(inputs["pao2_fio2"])
            if inputs.get("pao2_fio2") is not None
            else None
        ),
        mechanical_ventilation=bool(inputs.get("mechanical_ventilation", False)),
    )
