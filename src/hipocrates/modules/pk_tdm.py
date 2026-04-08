"""
pk_tdm.py — PK_TDM_Core v2.0

Farmacocinética de 1 compartimento y Monitoreo Terapéutico de Drogas (TDM).
Integrado al núcleo Hipócrates (SMNC-5+).

Modos soportados v1 (sin cambios):
  A. iv_bolus             — IV en bolo: C(t) = D/Vd · exp(−k·t)
  B. iv_infusion          — infusión IV simple + steady-state: C(t) = R₀/CL · (1 − exp(−k·t))
  C. multiple_dosing      — dosis repetidas IV u oral; factor de acumulación → Cmax_ss, Cmin_ss
  D. oral_bateman         — oral extravascular (ecuación de Bateman); caso degenerado ka≈k manejado
  E. target_dosing        — cálculo de LD, MD o ambos; verificación contra ventana terapéutica
  F. phenytoin_mm         — simulación Michaelis–Menten fenitoína paso a paso
  G. renal_adjustment     — ajuste proporcional de dosis por función renal (CLCr dado)

Modos nuevos v2 (añadidos en esta versión):
  H. cockcroft_gault          — cálculo de CLCr a partir de edad, sexo, peso, creatinina sérica
  I. target_dosing_renal      — target dosing con ajuste automático de CL por función renal
  J. tdm_bayes_map            — estimación bayesiana MAP básica para 1C a partir de concentraciones
                                observadas (sin Stan/PyMC/MCMC — optimización MAP pura, auditable)

LIMITACIONES EXPLÍCITAS v2.0:
  - Modelo de 1 compartimento únicamente (ni 2C ni multi-C)
  - Cockcroft-Gault: fórmula estándar; no se aplica a pediatría, embarazo, obesos mórbidos sin ajuste
  - Ajuste renal CL: proporcional simple (CL_adj = CL_base × CLCr_pac/CLCr_ref)
    No reemplaza modelos poblacionales específicos por fármaco
  - Bayes-MAP: optimización 1D/2D sobre CL (y Vd opcional) mediante búsqueda de sección dorada;
    asume estado estacionario (steady-state) en dosis múltiples; priors log-normales
    No usa Stan/PyMC/MCMC. No es equivalente a un software TDM validado clínicamente.
  - Sin interacciones farmacológicas, sin PK/PD
  - Intervalos de confianza no implementados (ci = None)
  - p = None, U = None, NB = None (no aplican a PK puro)

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from hipocrates.utils.types import Action, ClinicalOutput

# ─────────────────────────────────────────────────────────────────────────────
# Constantes internas
# ─────────────────────────────────────────────────────────────────────────────

_LN2 = math.log(2.0)
_KA_K_DEGENERATE_THRESHOLD = 1e-6  # |ka - k| < umbral → caso degenerado


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros PK base
# ─────────────────────────────────────────────────────────────────────────────

def calc_k(cl_L_h: float, vd_L: float) -> float:
    """
    Constante de eliminación de primer orden.
    k = CL / Vd  [h⁻¹]
    """
    return cl_L_h / vd_L


def calc_t_half(k: float) -> float:
    """
    Vida media de eliminación.
    t½ = ln(2) / k  [h]
    """
    return _LN2 / k


# ─────────────────────────────────────────────────────────────────────────────
# Modo A — IV bolus
# ─────────────────────────────────────────────────────────────────────────────

def pk_iv_bolus(
    dose_mg: float,
    vd_L: float,
    cl_L_h: float,
    time_h: float,
) -> dict[str, Any]:
    """
    Concentración plasmática tras IV en bolo (1 compartimento).
    C(t) = (D / Vd) · exp(−k · t)

    Args:
        dose_mg:  Dosis administrada [mg].
        vd_L:     Volumen de distribución [L].
        cl_L_h:   Clearance [L/h].
        time_h:   Tiempo post-bolo [h].

    Returns:
        Dict con parámetros calculados y concentración en t.
    """
    k = calc_k(cl_L_h, vd_L)
    t_half = calc_t_half(k)
    c0 = dose_mg / vd_L          # Concentración máxima inicial [mg/L]
    ct = c0 * math.exp(-k * time_h)
    return {
        "mode": "iv_bolus",
        "k_h": round(k, 6),
        "t_half_h": round(t_half, 4),
        "C0_mg_L": round(c0, 4),
        "Ct_mg_L": round(ct, 4),
        "time_h": time_h,
        "dose_mg": dose_mg,
        "vd_L": vd_L,
        "cl_L_h": cl_L_h,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo B — IV infusión
# ─────────────────────────────────────────────────────────────────────────────

def pk_iv_infusion(
    rate_mg_h: float,
    cl_L_h: float,
    vd_L: float,
    time_h: float,
) -> dict[str, Any]:
    """
    Concentración durante infusión IV a velocidad constante.
    C(t) = (R₀ / CL) · (1 − exp(−k · t))
    Css   = R₀ / CL  (steady-state teórico)

    Args:
        rate_mg_h: Velocidad de infusión [mg/h].
        cl_L_h:    Clearance [L/h].
        vd_L:      Volumen de distribución [L].
        time_h:    Duración de infusión [h].

    Returns:
        Dict con concentración a tiempo t y Css.
    """
    k = calc_k(cl_L_h, vd_L)
    t_half = calc_t_half(k)
    css = rate_mg_h / cl_L_h
    ct = css * (1.0 - math.exp(-k * time_h))
    # Fracción de Css alcanzada
    frac_css = ct / css if css > 0 else 0.0
    # Tiempo aproximado para 90% y 95% de Css
    t90 = -math.log(0.10) / k
    t95 = -math.log(0.05) / k
    return {
        "mode": "iv_infusion",
        "k_h": round(k, 6),
        "t_half_h": round(t_half, 4),
        "Css_mg_L": round(css, 4),
        "Ct_mg_L": round(ct, 4),
        "frac_of_Css": round(frac_css, 4),
        "t90pct_Css_h": round(t90, 2),
        "t95pct_Css_h": round(t95, 2),
        "time_h": time_h,
        "rate_mg_h": rate_mg_h,
        "cl_L_h": cl_L_h,
        "vd_L": vd_L,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo C — Dosis múltiples simples
# ─────────────────────────────────────────────────────────────────────────────

def pk_multiple_dosing(
    dose_mg: float,
    tau_h: float,
    cl_L_h: float,
    vd_L: float,
    time_h: float,
    route: str = "iv",
    F: float = 1.0,
) -> dict[str, Any]:
    """
    Concentración en steady-state tras dosis repetidas (1C, dosis múltiples).

    Para IV: factor de acumulación R = 1 / (1 − exp(−k·τ))
      Cmax_ss = (F·D / Vd) · R
      Cmin_ss = Cmax_ss · exp(−k·τ)
    Para oral: igual pero con F·D.

    Note: Fórmula supone steady-state ya alcanzado. Para concentración en
    tiempo t dentro del intervalo τ en SS, se usa:
      C(t) = Cmax_ss · exp(−k·t)

    Args:
        dose_mg: Dosis por intervalo [mg].
        tau_h:   Intervalo de dosificación [h].
        cl_L_h:  Clearance [L/h].
        vd_L:    Volumen de distribución [L].
        time_h:  Tiempo dentro del intervalo actual [h] (0 ≤ time_h ≤ tau_h).
        route:   'iv' o 'oral'.
        F:       Biodisponibilidad ∈ (0,1] (solo relevante para oral).

    Returns:
        Dict con Cmax_ss, Cmin_ss, factor de acumulación, Ct_ss.
    """
    k = calc_k(cl_L_h, vd_L)
    t_half = calc_t_half(k)
    ekt = math.exp(-k * tau_h)
    # Factor de acumulación
    accumulation_factor = 1.0 / (1.0 - ekt)
    # Concentración pico en SS
    cmax_ss = (F * dose_mg / vd_L) * accumulation_factor
    # Concentración valle en SS
    cmin_ss = cmax_ss * math.exp(-k * tau_h)
    # Concentración en t dentro del intervalo SS
    ct_ss = cmax_ss * math.exp(-k * time_h)
    # Número de semividas para alcanzar 90% SS
    n_halflives_90pct_ss = math.log(10.0) / math.log(2.0) * (tau_h / t_half)
    return {
        "mode": "multiple_dosing",
        "route": route,
        "k_h": round(k, 6),
        "t_half_h": round(t_half, 4),
        "accumulation_factor": round(accumulation_factor, 4),
        "Cmax_ss_mg_L": round(cmax_ss, 4),
        "Cmin_ss_mg_L": round(cmin_ss, 4),
        "Ct_ss_mg_L": round(ct_ss, 4),
        "time_within_interval_h": time_h,
        "tau_h": tau_h,
        "dose_mg": dose_mg,
        "F": F,
        "n_t_half_to_90pct_ss": round(n_halflives_90pct_ss, 2),
        "warning": (
            "Cmax_ss y Cmin_ss suponen steady-state ya alcanzado. "
            "No estimar Cmax_ss si no se han completado ≥4–5 semividas."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo D — Oral Bateman
# ─────────────────────────────────────────────────────────────────────────────

def pk_oral_bateman(
    dose_mg: float,
    F: float,
    ka_h: float,
    cl_L_h: float,
    vd_L: float,
    time_h: float,
) -> dict[str, Any]:
    """
    Concentración plasmática oral extravascular (ecuación de Bateman).

    C(t) = F·D·Ka / [Vd·(Ka − k)] · (exp(−k·t) − exp(−Ka·t))

    Caso degenerado ka ≈ k (|Ka − k| < umbral):
    Se usa la solución límite:
      C(t) = F·D·k·t / Vd · exp(−k·t)
    (límite de Bateman cuando Ka → k)

    Args:
        dose_mg: Dosis oral [mg].
        F:       Biodisponibilidad ∈ (0,1].
        ka_h:    Constante de absorción [h⁻¹].
        cl_L_h:  Clearance [L/h].
        vd_L:    Volumen de distribución [L].
        time_h:  Tiempo post-dosis [h].

    Returns:
        Dict con C(t), Tmax estimado y Cmax.
    """
    k = calc_k(cl_L_h, vd_L)
    t_half = calc_t_half(k)
    degenerate = abs(ka_h - k) < _KA_K_DEGENERATE_THRESHOLD

    if degenerate:
        # Límite analítico cuando ka → k
        ct = (F * dose_mg * k * time_h / vd_L) * math.exp(-k * time_h)
        tmax = 1.0 / k  # punto máximo del límite: d/dt = 0 → t = 1/k
        cmax = (F * dose_mg * k * (1.0 / k) / vd_L) * math.exp(-k * (1.0 / k))
        method = "bateman_limit_ka_approx_k"
    else:
        coef = (F * dose_mg * ka_h) / (vd_L * (ka_h - k))
        ct = coef * (math.exp(-k * time_h) - math.exp(-ka_h * time_h))
        # Tmax = ln(Ka/k) / (Ka − k)
        if ka_h > k:
            tmax = math.log(ka_h / k) / (ka_h - k)
        else:
            # ka < k: absorción más lenta que eliminación, Tmax diferente
            tmax = math.log(k / ka_h) / (k - ka_h)
        cmax = coef * (math.exp(-k * tmax) - math.exp(-ka_h * tmax))
        method = "bateman_standard"

    return {
        "mode": "oral_bateman",
        "method": method,
        "k_h": round(k, 6),
        "ka_h": round(ka_h, 6),
        "t_half_h": round(t_half, 4),
        "Ct_mg_L": round(max(ct, 0.0), 4),  # no puede ser negativo
        "Tmax_h": round(tmax, 4),
        "Cmax_mg_L": round(max(cmax, 0.0), 4),
        "time_h": time_h,
        "dose_mg": dose_mg,
        "F": F,
        "cl_L_h": cl_L_h,
        "vd_L": vd_L,
        "degenerate_case": degenerate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo E — Target dosing
# ─────────────────────────────────────────────────────────────────────────────

def pk_target_dosing(
    target_css_mg_L: float,
    cl_L_h: float,
    vd_L: float,
    tau_h: float,
    F: float,
    therapeutic_window: list[float],
    calc_type: str = "both",
) -> dict[str, Any]:
    """
    Cálculo de dosis objetivo para alcanzar Css deseado.

    Loading dose:    LD = target_Css · Vd / F
    Maintenance dose: MD = target_Css · CL · τ / F

    Verifica si LD y MD están dentro de la ventana terapéutica.

    Args:
        target_css_mg_L:    Css objetivo [mg/L].
        cl_L_h:             Clearance [L/h].
        vd_L:               Volumen de distribución [L].
        tau_h:              Intervalo de dosificación [h].
        F:                  Biodisponibilidad ∈ (0,1].
        therapeutic_window: [min_mg_L, max_mg_L] ventana terapéutica.
        calc_type:          'loading', 'maintenance', o 'both'.

    Returns:
        Dict con LD, MD (según calc_type), verificaciones de ventana.
    """
    tw_min, tw_max = therapeutic_window[0], therapeutic_window[1]
    k = calc_k(cl_L_h, vd_L)
    t_half = calc_t_half(k)

    result: dict[str, Any] = {
        "mode": "target_dosing",
        "calc_type": calc_type,
        "target_Css_mg_L": target_css_mg_L,
        "therapeutic_window_mg_L": therapeutic_window,
        "k_h": round(k, 6),
        "t_half_h": round(t_half, 4),
        "F": F,
        "tau_h": tau_h,
        "cl_L_h": cl_L_h,
        "vd_L": vd_L,
    }

    in_window_ld: Optional[bool] = None
    in_window_md: Optional[bool] = None

    if calc_type in ("loading", "both"):
        ld = target_css_mg_L * vd_L / F
        in_window_ld = tw_min <= target_css_mg_L <= tw_max
        result["loading_dose_mg"] = round(ld, 2)
        result["target_in_window"] = in_window_ld

    if calc_type in ("maintenance", "both"):
        md = target_css_mg_L * cl_L_h * tau_h / F
        # MD verifica que la Css objetivo esté dentro de la ventana
        in_window_md = tw_min <= target_css_mg_L <= tw_max
        result["maintenance_dose_mg"] = round(md, 2)
        result["maintenance_Css_mg_L"] = round(target_css_mg_L, 4)
        result["in_window"] = in_window_md

    # Bandera general de ventana
    if in_window_ld is not None or in_window_md is not None:
        result["target_within_therapeutic_window"] = (
            (in_window_ld if in_window_ld is not None else True) and
            (in_window_md if in_window_md is not None else True)
        )
    else:
        result["target_within_therapeutic_window"] = None

    result["limitation"] = (
        "LD y MD son aproximaciones de 1C lineal. "
        "Ajustar según niveles séricos reales y criterio clínico."
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Ajuste renal simple
# ─────────────────────────────────────────────────────────────────────────────

def renal_dose_adjustment(
    standard_dose_mg: float,
    clcr_patient_mL_min: float,
    clcr_ref_mL_min: float = 100.0,
) -> dict[str, Any]:
    """
    Ajuste proporcional de dosis por función renal (simplificado).

    new_dose = standard_dose × (CLCr_patient / CLCr_ref)

    LIMITACIÓN: Este es un ajuste proporcional simple.
    No reemplaza tablas de ajuste específicas por fármaco,
    modelos poblacionales, ni dosificación extendida para HD/DP.
    Solo aplicable a fármacos con eliminación renal predominante y
    cinética lineal. Consultar ficha técnica del fármaco.

    Args:
        standard_dose_mg:     Dosis estándar para CLCr de referencia [mg].
        clcr_patient_mL_min:  CLCr del paciente [mL/min].
        clcr_ref_mL_min:      CLCr de referencia (default 100 mL/min).

    Returns:
        Dict con dosis ajustada y ratio de ajuste.
    """
    ratio = clcr_patient_mL_min / clcr_ref_mL_min
    adjusted_dose = standard_dose_mg * ratio
    return {
        "mode": "renal_adjustment",
        "standard_dose_mg": round(standard_dose_mg, 2),
        "adjusted_dose_mg": round(adjusted_dose, 2),
        "clcr_patient_mL_min": round(clcr_patient_mL_min, 1),
        "clcr_ref_mL_min": round(clcr_ref_mL_min, 1),
        "dose_ratio": round(ratio, 4),
        "limitation": (
            "Ajuste proporcional simplificado. No reemplaza tablas de dosis "
            "específicas por fármaco. Solo para fármacos de eliminación renal "
            "predominante con cinética lineal."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo F — Michaelis–Menten fenitoína
# ─────────────────────────────────────────────────────────────────────────────

def pk_phenytoin_mm(
    vmax_mg_day: float,
    km_mg_L: float,
    dose_guess_mg_day: float,
    target_range_mg_L: list[float],
    dt_h: float = 1.0,
    max_days: float = 30.0,
    c0_mg_L: float = 0.0,
    vd_L: float = 50.0,
) -> dict[str, Any]:
    """
    Simulación de concentración fenitoína (Michaelis–Menten) paso a paso.

    dC/dt = D/Vd − (Vmax · C) / (Km + C)

    Integración numérica simple (Euler explícito) con ajuste iterativo
    de dosis hasta intentar alcanzar la ventana terapéutica.

    LIMITACIONES EXPLÍCITAS:
    - No es Bayes-MAP ni modelo poblacional.
    - Euler explícito: válido para dt pequeño (recomendado ≤1 h).
    - Vd fijo (default 50 L para adulto promedio). No personalizado.
    - Solo fenitoína libre aproximada. No modelamos fracción libre variable.
    - No considera interacciones farmacológicas.
    - Si no converge, se reporta honestamente sin ajuste forzado.

    Args:
        vmax_mg_day:       Velocidad máxima de eliminación [mg/día].
        km_mg_L:           Constante de Michaelis–Menten [mg/L].
        dose_guess_mg_day: Dosis inicial a simular [mg/día].
        target_range_mg_L: [min, max] ventana terapéutica [mg/L].
        dt_h:              Paso de integración [h]. Default 1 h.
        max_days:          Máximo de días de simulación. Default 30.
        c0_mg_L:           Concentración inicial [mg/L]. Default 0.
        vd_L:              Volumen de distribución [L]. Default 50.

    Returns:
        Dict con concentración final, estado de convergencia,
        dosis ajustada si converge, y trace resumido.
    """
    tw_min, tw_max = target_range_mg_L[0], target_range_mg_L[1]
    tw_mid = (tw_min + tw_max) / 2.0

    # Convertir Vmax a [mg/h] para consistencia con dt en horas
    vmax_mg_h = vmax_mg_day / 24.0

    # Estrategia: probar hasta 5 ajustes de dosis
    # Si Css no entra en ventana, reportarlo
    MAX_ITER_DOSE = 5
    best_result = None
    dose_trials: list[dict[str, Any]] = []
    current_dose_mg_day = dose_guess_mg_day
    converged = False
    final_dose = dose_guess_mg_day
    final_css = None

    for dose_iter in range(MAX_ITER_DOSE):
        dose_mg_h = current_dose_mg_day / 24.0
        c = c0_mg_L
        n_steps = int(max_days * 24.0 / dt_h)

        # Simular hasta steady-state (detectado como variación < 0.001 mg/L en 24 h)
        c_prev = c
        ss_reached = False
        for step in range(n_steps):
            elim = (vmax_mg_h * c) / (km_mg_L + c)
            dc = (dose_mg_h / vd_L - elim / vd_L) * dt_h
            c = max(c + dc, 0.0)  # no negativos
            # Chequear SS cada 24h
            if step > 0 and step % int(24.0 / dt_h) == 0:
                if abs(c - c_prev) < 0.001:
                    ss_reached = True
                    break
                c_prev = c

        # Verificar si Css está en ventana
        in_window = tw_min <= c <= tw_max
        trial = {
            "trial": dose_iter + 1,
            "dose_mg_day": round(current_dose_mg_day, 1),
            "Css_estimated_mg_L": round(c, 3),
            "in_window": in_window,
            "ss_reached": ss_reached,
        }
        dose_trials.append(trial)

        if in_window:
            converged = True
            final_dose = current_dose_mg_day
            final_css = c
            break

        # Ajuste de dosis hacia la mitad de la ventana objetivo
        # Usando la relación de MM: D ≈ Vmax·Css/(Km + Css)
        # Si c == 0, usar una estimación inicial
        if c < tw_min:
            # Necesitamos más dosis
            css_target = tw_mid
            new_dose = vmax_mg_day * css_target / (km_mg_L + css_target)
        else:
            # Dosis demasiado alta
            css_target = tw_mid
            new_dose = vmax_mg_day * css_target / (km_mg_L + css_target)

        # Evitar oscilación: promedio ponderado con la dosis previa
        new_dose = 0.6 * new_dose + 0.4 * current_dose_mg_day
        current_dose_mg_day = round(new_dose, 1)
        final_dose = current_dose_mg_day
        final_css = c

    if final_css is None:
        final_css = c

    return {
        "mode": "phenytoin_mm",
        "vmax_mg_day": vmax_mg_day,
        "km_mg_L": km_mg_L,
        "target_range_mg_L": target_range_mg_L,
        "initial_dose_mg_day": dose_guess_mg_day,
        "final_dose_mg_day": round(final_dose, 1),
        "Css_estimated_mg_L": round(final_css, 3),
        "in_therapeutic_window": converged,
        "dose_trials": dose_trials,
        "converged": converged,
        "warning": (
            "Simulación determinista MM con Euler explícito. No es Bayes-MAP. "
            "Vd fijo (50 L) — no personalizado. Verificar con niveles séricos reales. "
            "No considera interacciones ni fracción libre variable."
        ),
        "limitation": (
            "Esta simulación es orientativa. La fenitoína tiene cinética "
            "de saturación no lineal: pequeños cambios de dosis pueden causar "
            "grandes cambios de concentración. Siempre confirmar con niveles séricos."
        ) if not converged else (
            "Convergencia alcanzada in silico. Confirmar con niveles séricos reales "
            "antes de ajustar dosis."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# v2 — Modo H: Cockcroft-Gault
# ─────────────────────────────────────────────────────────────────────────────

def cockcroft_gault(
    age: float,
    sex: str,
    weight_kg: float,
    serum_creatinine_mg_dL: float,
) -> dict[str, Any]:
    """
    Estimación del aclaramiento de creatinina (CLCr) por la fórmula de Cockcroft-Gault.

    Hombre:   CLCr = [(140 − edad) × peso_kg] / [72 × creatinina_sérica_mg/dL]
    Mujer:    CLCr = [(140 − edad) × peso_kg] / [72 × creatinina_sérica_mg/dL] × 0.85

    LIMITACIONES EXPLÍCITAS:
    - Válido para adultos (≥18 años) con función renal estable.
    - No validado en: pediatría, embarazo, estados edematosos graves,
      obesidad mórbida sin ajuste de peso, amputaciones, insuficiencia hepática severa.
    - Usa peso corporal total (no peso ideal ni peso magro ajustado).
      En obesidad, considerar ajuste de peso según protocolo institucional.
    - Con creatinina sérica muy baja (p. ej., masa muscular reducida), puede sobreestimar CLCr.

    Args:
        age:                      Edad en años (> 0, adulto ≥18 recomendado).
        sex:                      'M' (masculino) o 'F' (femenino).
        weight_kg:                Peso corporal en kg (> 0).
        serum_creatinine_mg_dL:   Creatinina sérica en mg/dL (> 0).

    Returns:
        Dict con CLCr estimado [mL/min] e interpretación.
    """
    sex_upper = sex.strip().upper()
    if sex_upper not in ("M", "F"):
        raise PKInputError(f"'sex' debe ser 'M' o 'F', recibido: {sex!r}")

    clcr = ((140.0 - age) * weight_kg) / (72.0 * serum_creatinine_mg_dL)
    if sex_upper == "F":
        clcr *= 0.85
    clcr = max(clcr, 0.0)  # CLCr no puede ser negativo (caso teórico edad≥140)

    # Interpretación por etapa de enfermedad renal crónica (ERC) — CKD-EPI como referencia
    # CLCr Cockcroft-Gault no es idéntico a TFGe CKD-EPI, pero se usa como referencia clínica
    if clcr >= 90:
        interpretation = "Función renal normal o elevada (≥90 mL/min)"
    elif clcr >= 60:
        interpretation = "Deterioro renal leve (60–89 mL/min) — ERC etapa G2"
    elif clcr >= 30:
        interpretation = "Deterioro renal moderado (30–59 mL/min) — ERC etapa G3"
    elif clcr >= 15:
        interpretation = "Deterioro renal severo (15–29 mL/min) — ERC etapa G4"
    else:
        interpretation = "Insuficiencia renal avanzada (<15 mL/min) — ERC etapa G5 / considerar diálisis"

    return {
        "mode": "cockcroft_gault",
        "age_years": age,
        "sex": sex_upper,
        "weight_kg": weight_kg,
        "serum_creatinine_mg_dL": serum_creatinine_mg_dL,
        "clcr_mL_min": round(clcr, 1),
        "sex_correction_applied": (sex_upper == "F"),
        "interpretation": interpretation,
        "formula": (
            "CLCr = [(140-edad) × peso_kg] / [72 × Cr_mg/dL]"
            + (" × 0.85 (mujer)" if sex_upper == "F" else " (hombre)")
        ),
        "limitation": (
            "Cockcroft-Gault con peso total. Válido en adultos con función renal estable. "
            "No usar en pediatría, embarazo ni obesidad mórbida sin ajuste de peso. "
            "En masa muscular reducida puede sobreestimar CLCr."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# v2 — Modo I: Target dosing con ajuste renal automático
# ─────────────────────────────────────────────────────────────────────────────

def pk_target_dosing_renal(
    age: float,
    sex: str,
    weight_kg: float,
    serum_creatinine_mg_dL: float,
    base_cl_L_h: float,
    drug_clcr_reference_mL_min: float,
    vd_L: float,
    tau_h: float,
    F: float,
    target_css_mg_L: float,
    therapeutic_window: list[float],
    calc_type: str = "both",
) -> dict[str, Any]:
    """
    Target dosing con ajuste automático de clearance por función renal (Cockcroft-Gault).

    Flujo:
      1. Calcula CLCr del paciente (Cockcroft-Gault).
      2. Ajusta CL del fármaco: CL_adj = base_CL × (CLCr_pac / CLCr_ref)
      3. Calcula LD y/o MD con CL ajustado.

    SIMPLIFICACIÓN EXPLÍCITA:
    El ajuste es proporcional lineal (CL_adj = CL_base × ratio_renal).
    No es un modelo poblacional ni farmacogenético específico por fármaco.
    Solo aplicable a fármacos con eliminación renal predominantemente lineal.
    Consultar ficha técnica y modelos validados para el fármaco específico.

    Args:
        age:                        Edad en años.
        sex:                        'M' o 'F'.
        weight_kg:                  Peso en kg.
        serum_creatinine_mg_dL:     Creatinina sérica en mg/dL.
        base_cl_L_h:                CL poblacional de referencia [L/h] (para CLCr de referencia).
        drug_clcr_reference_mL_min: CLCr de referencia para el CL base del fármaco [mL/min].
        vd_L:                       Volumen de distribución [L].
        tau_h:                      Intervalo de dosificación [h].
        F:                          Biodisponibilidad (0, 1].
        target_css_mg_L:            Concentración en estado estacionario objetivo [mg/L].
        therapeutic_window:         [min, max] ventana terapéutica [mg/L].
        calc_type:                  'loading', 'maintenance', o 'both'.

    Returns:
        Dict con CLCr, CL ajustado, LD y/o MD, y advertencias.
    """
    # 1. Calcular CLCr del paciente
    cg_result = cockcroft_gault(age, sex, weight_kg, serum_creatinine_mg_dL)
    clcr_patient = cg_result["clcr_mL_min"]

    # 2. Ajuste proporcional de CL
    ratio = clcr_patient / drug_clcr_reference_mL_min
    cl_adjusted_L_h = base_cl_L_h * ratio

    # Protección: CL ajustado no puede ser 0 ni negativo
    if cl_adjusted_L_h <= 0:
        cl_adjusted_L_h = 0.001  # valor mínimo técnico; interpretación siempre debe dominar

    # 3. Target dosing con CL ajustado
    tw_min, tw_max = therapeutic_window[0], therapeutic_window[1]
    k = calc_k(cl_adjusted_L_h, vd_L)
    t_half = calc_t_half(k)

    result: dict[str, Any] = {
        "mode": "target_dosing_renal",
        "calc_type": calc_type,
        # Datos del paciente usados
        "age_years": age,
        "sex": sex.strip().upper(),
        "weight_kg": weight_kg,
        "serum_creatinine_mg_dL": serum_creatinine_mg_dL,
        # Función renal
        "clcr_patient_mL_min": clcr_patient,
        "clcr_reference_mL_min": drug_clcr_reference_mL_min,
        "clcr_ratio": round(ratio, 4),
        "renal_interpretation": cg_result["interpretation"],
        # CL
        "base_cl_L_h": round(base_cl_L_h, 4),
        "cl_adjusted_L_h": round(cl_adjusted_L_h, 4),
        "cl_adjustment_method": "CL_adj = CL_base × (CLCr_pac / CLCr_ref) — proporcional lineal",
        # PK derivada
        "vd_L": vd_L,
        "k_h": round(k, 6),
        "t_half_h": round(t_half, 4),
        "F": F,
        "tau_h": tau_h,
        "target_Css_mg_L": target_css_mg_L,
        "therapeutic_window_mg_L": therapeutic_window,
    }

    in_window = tw_min <= target_css_mg_L <= tw_max

    if calc_type in ("loading", "both"):
        ld = target_css_mg_L * vd_L / F
        result["loading_dose_mg"] = round(ld, 2)

    if calc_type in ("maintenance", "both"):
        md = target_css_mg_L * cl_adjusted_L_h * tau_h / F
        result["maintenance_dose_mg"] = round(md, 2)
        result["maintenance_Css_mg_L"] = round(target_css_mg_L, 4)

    result["target_within_therapeutic_window"] = in_window

    result["warning_simplification"] = (
        "Ajuste renal proporcional lineal (CL_adj = CL_base × CLCr/CLCr_ref). "
        "No es modelo poblacional PK/PD validado para este fármaco. "
        "Verificar con niveles séricos y ajustar según protocolo institucional."
    )
    result["limitation"] = (
        "LD y MD son estimaciones de 1C lineal con CL ajustado por Cockcroft-Gault. "
        "Confirmar con niveles séricos antes de cualquier decisión terapéutica."
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# v2 — Modo J: TDM Bayes-MAP básico (1 compartimento, sin scipy)
# ─────────────────────────────────────────────────────────────────────────────

def _golden_section_min(f: Any, a: float, b: float, tol: float = 1e-7, max_iter: int = 200) -> float:
    """
    Minimización univariante por sección dorada (golden section search).
    Implementación pura en Python — sin dependencias externas.

    Encuentra el mínimo de f en el intervalo [a, b].
    Supone que f es unimodal en dicho intervalo.

    Args:
        f:        Función escalar a minimizar.
        a, b:     Intervalo de búsqueda.
        tol:      Tolerancia de convergencia en la longitud del intervalo.
        max_iter: Iteraciones máximas.

    Returns:
        x óptimo aproximado en [a, b].
    """
    phi = (math.sqrt(5.0) - 1.0) / 2.0  # ≈ 0.618
    c = b - phi * (b - a)
    d = a + phi * (b - a)
    for _ in range(max_iter):
        if abs(b - a) < tol:
            break
        if f(c) < f(d):
            b = d
        else:
            a = c
        c = b - phi * (b - a)
        d = a + phi * (b - a)
    return (a + b) / 2.0


def _pk_ss_concentration(
    dose_mg: float,
    vd_L: float,
    cl_L_h: float,
    tau_h: float,
    t_h: float,
    F: float,
    route: str,
) -> float:
    """
    Concentración plasmática en estado estacionario (1C) para t horas tras la última dosis.

    Modelo múltiples dosis 1C:
      k = CL / Vd
      Cmax_ss = (F · D / Vd) / (1 − exp(−k · τ))     [IV bolo SS]
      C_ss(t) = Cmax_ss · exp(−k · t)

    Para ruta oral en SS (aproximación 1C sin absorción explícita):
      Se usa el mismo modelo — la absorción oral en SS queda subsumida en
      el F y en el perfil observado. Esta es la simplificación honesta de v2.

    NOTA: Este modelo asume steady-state ya alcanzado (≥4–5 t½).
    """
    k = cl_L_h / vd_L
    if k <= 0.0 or tau_h <= 0.0:
        return 0.0
    ekt = math.exp(-k * tau_h)
    if ekt >= 1.0:  # Protección numérica
        return 0.0
    cmax_ss = (F * dose_mg / vd_L) / (1.0 - ekt)
    ct = cmax_ss * math.exp(-k * t_h)
    return max(ct, 0.0)


def pk_tdm_bayes_map(
    dose_mg: float,
    tau_h: float,
    route: str,
    F: float,
    observed_concentrations: list[dict],
    prior_cl_mean_L_h: float,
    prior_cl_sd_L_h: float,
    prior_vd_mean_L: float,
    prior_vd_sd_L: float,
    sigma_obs_mg_L: float = 2.0,
    optimize_vd: bool = False,
) -> dict[str, Any]:
    """
    Estimación bayesiana MAP básica para fármaco de 1 compartimento.

    Calcula los parámetros posteriores (CL y opcionalmente Vd) que minimizan la
    función objetivo MAP: suma de error cuadrático ponderado + penalización de prior.

    Objetivo MAP (negativo log-posterior):
        L(CL, Vd) =
          Σ_i [ (C_obs_i − C_pred_i)² / (2 · σ_obs²) ]
          + (ln(CL) − ln(μ_CL))² / (2 · σ_ln_CL²)
          + (ln(Vd) − ln(μ_Vd))² / (2 · σ_ln_Vd²)

    donde σ_ln_X = σ_X / μ_X (aproximación log-normal de varianza pequeña).

    Optimización: sección dorada 1D o descenso coordenado 2D (si optimize_vd=True).
    Pure Python — sin scipy.

    SUPUESTOS EXPLÍCITOS:
    - Estado estacionario ya alcanzado (steady-state).
    - Modelo 1C lineal con absorción instantánea efectiva (oral subsumido en F).
    - Priors log-normales (aproximados como gaussianos en escala log).
    - Una sola observación es válida pero produce estimaciones menos informadas.
    - No es un software TDM validado clínicamente. No reemplaza InsightRx, TCIWorks,
      DoseMe, o cualquier herramienta TDM validada con modelos poblacionales específicos.

    Args:
        dose_mg:                   Dosis por intervalo [mg].
        tau_h:                     Intervalo de dosificación [h].
        route:                     'iv' u 'oral' (solo afecta etiquetado; F maneja biodisponibilidad).
        F:                         Biodisponibilidad (0, 1].
        observed_concentrations:   Lista de dicts: [{"time_h": t, "conc_mg_L": c}, ...].
                                   time_h: tiempo post-última dosis en SS [h].
                                   conc_mg_L: concentración observada [mg/L].
        prior_cl_mean_L_h:         Media prior del CL [L/h].
        prior_cl_sd_L_h:           Desviación estándar del prior del CL [L/h].
        prior_vd_mean_L:           Media prior del Vd [L].
        prior_vd_sd_L:             Desviación estándar del prior del Vd [L].
        sigma_obs_mg_L:            Error de observación asumido [mg/L]. Default 2.0.
        optimize_vd:               Si True, también optimiza Vd (descenso coordenado).
                                   Si False (default), Vd queda fijo en prior_vd_mean_L.

    Returns:
        Dict con parámetros estimados, predicciones, sugerencia de ajuste y limitaciones.
    """
    # ── Validación de observaciones ──────────────────────────────────────────
    if not observed_concentrations:
        raise PKInputError("'observed_concentrations' no puede estar vacío.")

    obs: list[tuple[float, float]] = []
    for i, o in enumerate(observed_concentrations):
        if not isinstance(o, dict) or "time_h" not in o or "conc_mg_L" not in o:
            raise PKInputError(
                f"Observación {i} mal formada: debe ser dict con 'time_h' y 'conc_mg_L'. "
                f"Recibido: {o!r}"
            )
        t = float(o["time_h"])
        c = float(o["conc_mg_L"])
        if not math.isfinite(t) or not math.isfinite(c):
            raise PKInputError(f"Observación {i}: time_h o conc_mg_L no finitos.")
        if t < 0:
            raise PKInputError(f"Observación {i}: 'time_h' debe ser ≥ 0, recibido: {t}")
        if c < 0:
            raise PKInputError(f"Observación {i}: 'conc_mg_L' debe ser ≥ 0, recibido: {c}")
        obs.append((t, c))

    sigma2_obs = sigma_obs_mg_L ** 2
    if sigma2_obs <= 0:
        sigma2_obs = 4.0  # fallback seguro

    # ── Prior log-normal (aproximación): σ_ln ≈ σ / μ ────────────────────────
    sigma_ln_cl = prior_cl_sd_L_h / prior_cl_mean_L_h if prior_cl_mean_L_h > 0 else 0.5
    sigma_ln_vd = prior_vd_sd_L / prior_vd_mean_L if prior_vd_mean_L > 0 else 0.5
    ln_mu_cl = math.log(prior_cl_mean_L_h)
    ln_mu_vd = math.log(prior_vd_mean_L)

    # ── Función objetivo MAP ──────────────────────────────────────────────────
    def map_objective(cl: float, vd: float) -> float:
        """Negativo del log-posterior (a minimizar)."""
        if cl <= 0.0 or vd <= 0.0:
            return 1e12
        # Término de verosimilitud (error cuadrático)
        lik = 0.0
        for t_obs, c_obs in obs:
            c_pred = _pk_ss_concentration(dose_mg, vd, cl, tau_h, t_obs, F, route)
            lik += (c_obs - c_pred) ** 2 / (2.0 * sigma2_obs)
        # Términos de prior (log-normal)
        prior_cl = (math.log(cl) - ln_mu_cl) ** 2 / (2.0 * sigma_ln_cl ** 2)
        prior_vd = (math.log(vd) - ln_mu_vd) ** 2 / (2.0 * sigma_ln_vd ** 2)
        return lik + prior_cl + prior_vd

    # ── Rango de búsqueda: [0.1 × prior, 10 × prior] ─────────────────────────
    cl_lo = max(prior_cl_mean_L_h * 0.05, 0.001)
    cl_hi = prior_cl_mean_L_h * 20.0
    vd_lo = max(prior_vd_mean_L * 0.05, 0.1)
    vd_hi = prior_vd_mean_L * 20.0

    # ── Optimización ─────────────────────────────────────────────────────────
    if optimize_vd:
        # Descenso coordenado: alternar optimización CL y Vd
        cl_est = prior_cl_mean_L_h
        vd_est = prior_vd_mean_L
        for _ in range(20):  # Máximo 20 ciclos de coordenadas
            cl_prev, vd_prev = cl_est, vd_est
            # Optimizar CL con Vd fijo
            cl_est = _golden_section_min(lambda cl: map_objective(cl, vd_est), cl_lo, cl_hi)
            # Optimizar Vd con CL fijo
            vd_est = _golden_section_min(lambda vd: map_objective(cl_est, vd), vd_lo, vd_hi)
            # Convergencia
            if abs(cl_est - cl_prev) < 1e-6 and abs(vd_est - vd_prev) < 1e-6:
                break
        optimization_method = "Descenso coordenado (2D): CL y Vd optimizados"
    else:
        # Solo optimizar CL, Vd fijo en prior
        vd_est = prior_vd_mean_L
        cl_est = _golden_section_min(lambda cl: map_objective(cl, vd_est), cl_lo, cl_hi)
        optimization_method = "Sección dorada (1D): CL optimizado, Vd fijo en prior"

    # ── Predicciones con parámetros estimados ─────────────────────────────────
    k_est = cl_est / vd_est
    t_half_est = _LN2 / k_est if k_est > 0 else float("inf")

    predicted: list[dict[str, Any]] = []
    for t_obs, c_obs in obs:
        c_pred = _pk_ss_concentration(dose_mg, vd_est, cl_est, tau_h, t_obs, F, route)
        predicted.append({
            "time_h": t_obs,
            "conc_obs_mg_L": round(c_obs, 4),
            "conc_pred_mg_L": round(c_pred, 4),
            "error_mg_L": round(c_obs - c_pred, 4),
        })

    # ── Predicción de Cmin y Cmax en SS con parámetros estimados ─────────────
    cmax_pred = _pk_ss_concentration(dose_mg, vd_est, cl_est, tau_h, 0.0, F, route)
    cmin_pred = _pk_ss_concentration(dose_mg, vd_est, cl_est, tau_h, tau_h, F, route)

    # ── Sugerencia de ajuste de dosis (orientativa) ───────────────────────────
    # Basado en ajuste proporcional: nueva_D = D × (Css_objetivo / Css_actual)
    css_current_estimate = (cmax_pred + cmin_pred) / 2.0
    dose_suggestion_text = (
        "Con los parámetros estimados MAP, revisar si el perfil predicho "
        "está dentro de la ventana terapéutica deseada. "
        "Si se requiere ajuste, usar: D_nueva = D × (Css_objetivo / Css_estimada). "
        "Confirmación con niveles séricos adicionales es obligatoria antes de ajustar."
    )

    return {
        "mode": "tdm_bayes_map",
        "prior_parameters": {
            "cl_mean_L_h": prior_cl_mean_L_h,
            "cl_sd_L_h": prior_cl_sd_L_h,
            "vd_mean_L": prior_vd_mean_L,
            "vd_sd_L": prior_vd_sd_L,
        },
        "observations_used": len(obs),
        "observations_detail": [{"time_h": t, "conc_mg_L": c} for t, c in obs],
        "optimization_method": optimization_method,
        "cl_estimated_L_h": round(cl_est, 4),
        "vd_estimated_L": round(vd_est, 4),
        "k_estimated_h": round(k_est, 6),
        "t_half_estimated_h": round(t_half_est, 3),
        "vd_was_optimized": optimize_vd,
        "posterior_map_summary": (
            f"CL_MAP = {round(cl_est, 4)} L/h "
            f"(prior: {prior_cl_mean_L_h} ± {prior_cl_sd_L_h} L/h), "
            f"Vd_MAP = {round(vd_est, 4)} L "
            f"(prior: {prior_vd_mean_L} ± {prior_vd_sd_L} L)"
        ),
        "predicted_concentrations": predicted,
        "cmax_ss_predicted_mg_L": round(cmax_pred, 4),
        "cmin_ss_predicted_mg_L": round(cmin_pred, 4),
        "css_average_estimated_mg_L": round(css_current_estimate, 4),
        "dose_adjustment_suggestion": dose_suggestion_text,
        "sigma_obs_assumed_mg_L": sigma_obs_mg_L,
        "limitations": [
            "Estimación MAP básica para 1 compartimento. No es un TDM validado clínicamente.",
            "Supone estado estacionario (steady-state) ya alcanzado (≥4–5 semividas).",
            "Modelo oral usa misma ecuación que IV con F — absorción oral no modelada explícitamente.",
            "No reemplaza InsightRx, DoseMe, TCIWorks u otros software TDM con modelos poblacionales validados.",
            "Con 1 sola observación, CL y Vd pueden ser mal identificables — el prior domina la estimación.",
            "No incorpora variabilidad intraindividual ni errores de tiempo de muestreo.",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validación de inputs por modo
# ─────────────────────────────────────────────────────────────────────────────

class PKInputError(ValueError):
    """Error de validación de inputs PK."""
    pass


def _require_positive(inputs: dict, key: str) -> float:
    """Verifica que la clave exista y sea > 0."""
    if key not in inputs:
        raise PKInputError(f"Campo requerido ausente: '{key}'")
    try:
        v = float(inputs[key])
    except (TypeError, ValueError):
        raise PKInputError(f"'{key}' debe ser numérico, recibido: {inputs[key]!r}")
    if not math.isfinite(v):
        raise PKInputError(f"'{key}' no puede ser NaN o infinito: {v}")
    if v <= 0.0:
        raise PKInputError(f"'{key}' debe ser > 0, recibido: {v}")
    return v


def _require_nonneg(inputs: dict, key: str) -> float:
    """Verifica que la clave exista y sea >= 0."""
    if key not in inputs:
        raise PKInputError(f"Campo requerido ausente: '{key}'")
    try:
        v = float(inputs[key])
    except (TypeError, ValueError):
        raise PKInputError(f"'{key}' debe ser numérico, recibido: {inputs[key]!r}")
    if not math.isfinite(v):
        raise PKInputError(f"'{key}' no puede ser NaN o infinito: {v}")
    if v < 0.0:
        raise PKInputError(f"'{key}' debe ser >= 0, recibido: {v}")
    return v


def _require_bioavailability(inputs: dict, key: str = "F") -> float:
    """Verifica biodisponibilidad en (0, 1]."""
    if key not in inputs:
        return 1.0  # default IV = 100%
    try:
        v = float(inputs[key])
    except (TypeError, ValueError):
        raise PKInputError(f"'{key}' debe ser numérico, recibido: {inputs[key]!r}")
    if not math.isfinite(v):
        raise PKInputError(f"'{key}' no puede ser NaN o infinito: {v}")
    if not (0.0 < v <= 1.0):
        raise PKInputError(f"'{key}' (biodisponibilidad) debe estar en (0, 1], recibido: {v}")
    return v


def _require_therapeutic_window(inputs: dict, key: str = "therapeutic_window") -> list[float]:
    """Verifica que la ventana terapéutica sea [min, max] con min < max y ambos >= 0."""
    if key not in inputs:
        raise PKInputError(f"Campo requerido ausente: '{key}'")
    tw = inputs[key]
    if not isinstance(tw, (list, tuple)) or len(tw) != 2:
        raise PKInputError(f"'{key}' debe ser [min, max], recibido: {tw!r}")
    try:
        lo, hi = float(tw[0]), float(tw[1])
    except (TypeError, ValueError):
        raise PKInputError(f"'{key}' debe contener valores numéricos, recibido: {tw!r}")
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise PKInputError(f"'{key}' contiene valores no finitos: {tw!r}")
    if lo < 0.0 or hi < 0.0:
        raise PKInputError(f"'{key}' no puede contener valores negativos: {tw!r}")
    if lo >= hi:
        raise PKInputError(f"'{key}' debe tener min < max, recibido: {tw!r}")
    return [lo, hi]


# ─────────────────────────────────────────────────────────────────────────────
# Lógica de acción y salida homogénea
# ─────────────────────────────────────────────────────────────────────────────

def _action_for_pk(pk_result: dict[str, Any]) -> str:
    """
    Determina la acción canónica según el resultado PK.

    Lógica:
    - target_dosing → siempre review_dosing
      (el cálculo de LD/MD es orientativo; la decisión terapéutica final
      corresponde al clínico con niveles séricos reales confirmados)
    - phenytoin_mm → review_dosing en ambos casos (convergió o no)
      (la simulación MM es determinista y no sustituye TDM real)
    - iv_bolus / iv_infusion / multiple_dosing / oral_bateman / renal_adjustment
      → observe (información farmacocinética, sin recomendación de dosis directa)

    Nota de diseño: PK_TDM_Core v2.0 nunca emite start_treatment.
    Los cálculos PK son apoyo orientativo, no prescripción autónoma.
    """
    mode = pk_result.get("mode", "")

    if mode == "target_dosing":
        # review_dosing independientemente de si el target cae dentro o fuera de ventana.
        # El cálculo 1C lineal es una estimación inicial; siempre requiere
        # confirmación con niveles séricos antes de tomar decisión terapéutica.
        return Action.REVIEW_DOSING

    elif mode == "phenytoin_mm":
        # review_dosing tanto si converge como si no.
        # La simulación Euler-MM es orientativa; la cinética de saturación de
        # fenitoína hace que pequeños cambios produzcan grandes variaciones.
        return Action.REVIEW_DOSING

    elif mode == "renal_adjustment":
        return Action.OBSERVE

    elif mode == "cockcroft_gault":
        # Solo calcula CLCr — información farmacocinética, sin recomendación de dosis
        return Action.OBSERVE

    elif mode == "target_dosing_renal":
        # Ajuste de dosis con función renal automática — siempre review_dosing
        # (como target_dosing v1, pero con capa renal adicional que requiere confirmación)
        return Action.REVIEW_DOSING

    elif mode == "tdm_bayes_map":
        # Estimación MAP: apoyo a dosificación, nunca prescripción autónoma
        return Action.REVIEW_DOSING

    else:
        # iv_bolus, iv_infusion, multiple_dosing, oral_bateman
        return Action.OBSERVE


def _explain_for_pk(pk_result: dict[str, Any], mode: str) -> str:
    """Genera el texto explain según el modo PK."""
    if mode == "iv_bolus":
        return (
            f"IV bolus: D={pk_result['dose_mg']} mg, Vd={pk_result['vd_L']} L, "
            f"CL={pk_result['cl_L_h']} L/h. "
            f"k={pk_result['k_h']} h⁻¹, t½={pk_result['t_half_h']} h. "
            f"C(t={pk_result['time_h']}h) = {pk_result['Ct_mg_L']} mg/L "
            f"(C₀={pk_result['C0_mg_L']} mg/L). "
            f"Modelo 1C. Confirmar con niveles séricos."
        )
    elif mode == "iv_infusion":
        return (
            f"Infusión IV: tasa={pk_result['rate_mg_h']} mg/h. "
            f"Css(steady-state) = {pk_result['Css_mg_L']} mg/L. "
            f"C(t={pk_result['time_h']}h) = {pk_result['Ct_mg_L']} mg/L "
            f"({pk_result['frac_of_Css']*100:.1f}% del Css). "
            f"t½={pk_result['t_half_h']} h. 90% Css a las {pk_result['t90pct_Css_h']} h."
        )
    elif mode == "multiple_dosing":
        return (
            f"Dosis múltiples ({pk_result['route']}): D={pk_result['dose_mg']} mg "
            f"cada {pk_result['tau_h']} h. "
            f"Cmax_ss={pk_result['Cmax_ss_mg_L']} mg/L, Cmin_ss={pk_result['Cmin_ss_mg_L']} mg/L. "
            f"Factor acumulación={pk_result['accumulation_factor']}. "
            f"t½={pk_result['t_half_h']} h. {pk_result['warning']}"
        )
    elif mode == "oral_bateman":
        degen = " [caso degenerado: ka≈k, solución límite usada]" if pk_result.get("degenerate_case") else ""
        return (
            f"Oral Bateman{degen}: D={pk_result['dose_mg']} mg, F={pk_result['F']}. "
            f"Tmax={pk_result['Tmax_h']} h, Cmax={pk_result['Cmax_mg_L']} mg/L. "
            f"C(t={pk_result['time_h']}h) = {pk_result['Ct_mg_L']} mg/L. "
            f"t½={pk_result['t_half_h']} h. Modelo 1C lineal."
        )
    elif mode == "target_dosing":
        in_w = pk_result.get("target_within_therapeutic_window", False)
        ld = pk_result.get("loading_dose_mg")
        md = pk_result.get("maintenance_dose_mg")
        parts = [f"Target dosing: Css objetivo={pk_result['target_Css_mg_L']} mg/L."]
        if ld is not None:
            parts.append(f"LD={ld} mg.")
        if md is not None:
            parts.append(f"MD={md} mg/τ.")
        parts.append(
            f"Ventana terapéutica {pk_result['therapeutic_window_mg_L']} mg/L: "
            f"{'✓ dentro' if in_w else '✗ fuera'}. {pk_result['limitation']}"
        )
        return " ".join(parts)
    elif mode == "phenytoin_mm":
        trials = len(pk_result.get("dose_trials", []))
        return (
            f"Fenitoína MM: Vmax={pk_result['vmax_mg_day']} mg/día, "
            f"Km={pk_result['km_mg_L']} mg/L. "
            f"{'Convergencia en' if pk_result['converged'] else 'Sin convergencia en'} "
            f"{trials} ensayo(s). "
            f"Dosis final={pk_result['final_dose_mg_day']} mg/día, "
            f"Css estimado={pk_result['Css_estimated_mg_L']} mg/L. "
            f"{pk_result['warning']}"
        )
    elif mode == "renal_adjustment":
        return (
            f"Ajuste renal: dosis estándar={pk_result['standard_dose_mg']} mg, "
            f"CLCr={pk_result['clcr_patient_mL_min']} mL/min "
            f"(ref {pk_result['clcr_ref_mL_min']} mL/min), "
            f"ratio={pk_result['dose_ratio']}, "
            f"dosis ajustada={pk_result['adjusted_dose_mg']} mg. "
            f"{pk_result['limitation']}"
        )
    elif mode == "cockcroft_gault":
        return (
            f"Cockcroft-Gault: {pk_result.get('age_years')} años, "
            f"{'hombre' if pk_result.get('sex') == 'M' else 'mujer'}, "
            f"{pk_result.get('weight_kg')} kg, Cr={pk_result.get('serum_creatinine_mg_dL')} mg/dL. "
            f"CLCr estimado = {pk_result.get('clcr_mL_min')} mL/min. "
            f"{pk_result.get('interpretation')}. "
            f"{pk_result.get('limitation')}"
        )
    elif mode == "target_dosing_renal":
        ld = pk_result.get("loading_dose_mg")
        md = pk_result.get("maintenance_dose_mg")
        parts = [
            f"Target dosing renal: CLCr={pk_result.get('clcr_patient_mL_min')} mL/min, "
            f"CL_base={pk_result.get('base_cl_L_h')} L/h → "
            f"CL_ajustado={pk_result.get('cl_adjusted_L_h')} L/h "
            f"(ratio={pk_result.get('clcr_ratio')}). "
            f"Css objetivo={pk_result.get('target_Css_mg_L')} mg/L."
        ]
        if ld is not None:
            parts.append(f"LD={ld} mg.")
        if md is not None:
            parts.append(f"MD={md} mg/τ.")
        parts.append(pk_result.get("warning_simplification", ""))
        return " ".join(parts)
    elif mode == "tdm_bayes_map":
        return (
            f"TDM Bayes-MAP: {pk_result.get('observations_used')} observación(es) usada(s). "
            f"CL_MAP={pk_result.get('cl_estimated_L_h')} L/h "
            f"(prior: {pk_result.get('prior_parameters', {}).get('cl_mean_L_h')} L/h), "
            f"Vd_MAP={pk_result.get('vd_estimated_L')} L. "
            f"Cmax_ss predicho={pk_result.get('cmax_ss_predicted_mg_L')} mg/L, "
            f"Cmin_ss predicho={pk_result.get('cmin_ss_predicted_mg_L')} mg/L. "
            f"Estimación orientativa — confirmar con niveles séricos. "
            f"Acción: revisar dosificación."
        )
    return f"PK_TDM_Core modo {mode}. Ver result para detalle."


# ─────────────────────────────────────────────────────────────────────────────
# Interfaz estándar del módulo
# ─────────────────────────────────────────────────────────────────────────────

def run(clinical_input_dict: dict[str, Any]) -> ClinicalOutput:
    """
    Interfaz estándar del módulo PK_TDM_Core.

    Campos en inputs:
      - mode: str — uno de:
          v1: iv_bolus, iv_infusion, multiple_dosing,
              oral_bateman, target_dosing, phenytoin_mm, renal_adjustment
          v2: cockcroft_gault, target_dosing_renal, tdm_bayes_map
      - (resto de campos según modo; ver docstring de cada función)

    Raises:
        PKInputError: Si algún input requerido falta o es inválido.
    """
    inp = clinical_input_dict["inputs"]
    mode = inp.get("mode", "")
    if not isinstance(mode, str) or not mode.strip():
        raise PKInputError("Campo 'mode' requerido en inputs. "
                           "Opciones: iv_bolus, iv_infusion, multiple_dosing, "
                           "oral_bateman, target_dosing, phenytoin_mm, renal_adjustment")

    # ── Modo A: iv_bolus ──────────────────────────────────────────────────────
    if mode == "iv_bolus":
        dose_mg = _require_positive(inp, "dose_mg")
        vd_L    = _require_positive(inp, "vd_L")
        cl_L_h  = _require_positive(inp, "cl_L_h")
        time_h  = _require_nonneg(inp, "time_h")
        pk_r = pk_iv_bolus(dose_mg, vd_L, cl_L_h, time_h)

    # ── Modo B: iv_infusion ───────────────────────────────────────────────────
    elif mode == "iv_infusion":
        rate_mg_h = _require_positive(inp, "rate_mg_h")
        cl_L_h    = _require_positive(inp, "cl_L_h")
        vd_L      = _require_positive(inp, "vd_L")
        time_h    = _require_nonneg(inp, "time_h")
        pk_r = pk_iv_infusion(rate_mg_h, cl_L_h, vd_L, time_h)

    # ── Modo C: multiple_dosing ───────────────────────────────────────────────
    elif mode == "multiple_dosing":
        dose_mg = _require_positive(inp, "dose_mg")
        tau_h   = _require_positive(inp, "tau_h")
        cl_L_h  = _require_positive(inp, "cl_L_h")
        vd_L    = _require_positive(inp, "vd_L")
        time_h  = _require_nonneg(inp, "time_h")
        F       = _require_bioavailability(inp, "F")
        route   = inp.get("route", "iv")
        if route not in ("iv", "oral"):
            raise PKInputError(f"'route' debe ser 'iv' o 'oral', recibido: {route!r}")
        pk_r = pk_multiple_dosing(dose_mg, tau_h, cl_L_h, vd_L, time_h, route, F)

    # ── Modo D: oral_bateman ──────────────────────────────────────────────────
    elif mode == "oral_bateman":
        dose_mg = _require_positive(inp, "dose_mg")
        F       = _require_bioavailability(inp, "F")
        ka_h    = _require_positive(inp, "ka_h")
        cl_L_h  = _require_positive(inp, "cl_L_h")
        vd_L    = _require_positive(inp, "vd_L")
        time_h  = _require_nonneg(inp, "time_h")
        pk_r = pk_oral_bateman(dose_mg, F, ka_h, cl_L_h, vd_L, time_h)

    # ── Modo E: target_dosing ─────────────────────────────────────────────────
    elif mode == "target_dosing":
        target_css = _require_positive(inp, "target_css_mg_L")
        cl_L_h     = _require_positive(inp, "cl_L_h")
        vd_L       = _require_positive(inp, "vd_L")
        tau_h      = _require_positive(inp, "tau_h")
        F          = _require_bioavailability(inp, "F")
        tw         = _require_therapeutic_window(inp, "therapeutic_window")
        calc_type  = inp.get("calc_type", "both")
        if calc_type not in ("loading", "maintenance", "both"):
            raise PKInputError(f"'calc_type' debe ser 'loading', 'maintenance' o 'both'.")
        pk_r = pk_target_dosing(target_css, cl_L_h, vd_L, tau_h, F, tw, calc_type)

    # ── Modo F: phenytoin_mm ──────────────────────────────────────────────────
    elif mode == "phenytoin_mm":
        vmax        = _require_positive(inp, "vmax_mg_day")
        km          = _require_positive(inp, "km_mg_L")
        dose_guess  = _require_positive(inp, "dose_guess_mg_day")
        tw          = _require_therapeutic_window(inp, "target_range_mg_L")
        dt_h        = float(inp.get("dt_h", 1.0))
        max_days    = float(inp.get("max_days", 30.0))
        c0          = float(inp.get("c0_mg_L", 0.0))
        vd_L_mm     = float(inp.get("vd_L", 50.0))
        if dt_h <= 0 or dt_h > 24:
            raise PKInputError(f"'dt_h' debe estar en (0, 24], recibido: {dt_h}")
        if max_days <= 0:
            raise PKInputError(f"'max_days' debe ser > 0, recibido: {max_days}")
        if c0 < 0:
            raise PKInputError(f"'c0_mg_L' debe ser >= 0, recibido: {c0}")
        if vd_L_mm <= 0:
            raise PKInputError(f"'vd_L' debe ser > 0, recibido: {vd_L_mm}")
        pk_r = pk_phenytoin_mm(vmax, km, dose_guess, tw, dt_h, max_days, c0, vd_L_mm)

    # ── Modo G: renal_adjustment ──────────────────────────────────────────────
    elif mode == "renal_adjustment":
        std_dose    = _require_positive(inp, "standard_dose_mg")
        clcr_pat    = _require_positive(inp, "clcr_patient_mL_min")
        clcr_ref    = float(inp.get("clcr_ref_mL_min", 100.0))
        if clcr_ref <= 0:
            raise PKInputError(f"'clcr_ref_mL_min' debe ser > 0, recibido: {clcr_ref}")
        pk_r = renal_dose_adjustment(std_dose, clcr_pat, clcr_ref)

    # ── Modo H v2: cockcroft_gault ────────────────────────────────────────────
    elif mode == "cockcroft_gault":
        age     = _require_positive(inp, "age")
        sex     = inp.get("sex", "")
        if not isinstance(sex, str) or sex.strip().upper() not in ("M", "F"):
            raise PKInputError(f"'sex' debe ser 'M' o 'F', recibido: {sex!r}")
        weight  = _require_positive(inp, "weight_kg")
        scr     = _require_positive(inp, "serum_creatinine_mg_dL")
        pk_r = cockcroft_gault(age, sex, weight, scr)

    # ── Modo I v2: target_dosing_renal ────────────────────────────────────────
    elif mode == "target_dosing_renal":
        age     = _require_positive(inp, "age")
        sex     = inp.get("sex", "")
        if not isinstance(sex, str) or sex.strip().upper() not in ("M", "F"):
            raise PKInputError(f"'sex' debe ser 'M' o 'F', recibido: {sex!r}")
        weight  = _require_positive(inp, "weight_kg")
        scr     = _require_positive(inp, "serum_creatinine_mg_dL")
        base_cl = _require_positive(inp, "base_cl_L_h")
        clcr_ref = _require_positive(inp, "drug_clcr_reference_mL_min")
        vd_L    = _require_positive(inp, "vd_L")
        tau_h   = _require_positive(inp, "tau_h")
        F       = _require_bioavailability(inp, "F")
        target_css = _require_positive(inp, "target_css_mg_L")
        tw      = _require_therapeutic_window(inp, "therapeutic_window")
        calc_type = inp.get("calc_type", "both")
        if calc_type not in ("loading", "maintenance", "both"):
            raise PKInputError(f"'calc_type' debe ser 'loading', 'maintenance' o 'both'.")
        pk_r = pk_target_dosing_renal(
            age, sex, weight, scr, base_cl, clcr_ref,
            vd_L, tau_h, F, target_css, tw, calc_type
        )

    # ── Modo J v2: tdm_bayes_map ──────────────────────────────────────────────
    elif mode == "tdm_bayes_map":
        dose_mg        = _require_positive(inp, "dose_mg")
        tau_h          = _require_positive(inp, "tau_h")
        route          = inp.get("route", "iv")
        if route not in ("iv", "oral"):
            raise PKInputError(f"'route' debe ser 'iv' u 'oral', recibido: {route!r}")
        F              = _require_bioavailability(inp, "F")
        obs_list       = inp.get("observed_concentrations")
        if not isinstance(obs_list, list) or len(obs_list) == 0:
            raise PKInputError(
                "'observed_concentrations' debe ser una lista no vacía de "
                "dicts {time_h, conc_mg_L}."
            )
        prior_cl_mean  = _require_positive(inp, "prior_cl_mean_L_h")
        prior_cl_sd    = _require_positive(inp, "prior_cl_sd_L_h")
        prior_vd_mean  = _require_positive(inp, "prior_vd_mean_L")
        prior_vd_sd    = _require_positive(inp, "prior_vd_sd_L")
        sigma_obs      = float(inp.get("sigma_obs_mg_L", 2.0))
        if sigma_obs <= 0 or not math.isfinite(sigma_obs):
            raise PKInputError(f"'sigma_obs_mg_L' debe ser > 0, recibido: {sigma_obs}")
        optimize_vd    = bool(inp.get("optimize_vd", False))
        pk_r = pk_tdm_bayes_map(
            dose_mg, tau_h, route, F, obs_list,
            prior_cl_mean, prior_cl_sd,
            prior_vd_mean, prior_vd_sd,
            sigma_obs, optimize_vd,
        )

    else:
        raise PKInputError(
            f"Modo '{mode}' no reconocido. "
            f"v1: iv_bolus, iv_infusion, multiple_dosing, oral_bateman, "
            f"target_dosing, phenytoin_mm, renal_adjustment. "
            f"v2: cockcroft_gault, target_dosing_renal, tdm_bayes_map."
        )

    action = _action_for_pk(pk_r)
    explain = _explain_for_pk(pk_r, mode)

    return ClinicalOutput(
        result=pk_r,
        action=action,
        p=None,
        U=None,
        NB=None,
        units_ok=True,  # El gate lo confirma; aquí es True tras pasar validación interna
        explain=explain,
        ci=None,        # v1.0: sin intervalos de confianza implementados
    )
