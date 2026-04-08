"""
dca.py — DCA_Utility_Module

Decision Curve Analysis (SMNC-5+, §5.4).

Implementa:
  - Cálculo de Beneficio Neto (NB) como función del umbral θ:
      NB(θ) = TP/N − FP/N × (θ / (1 − θ))
  - Modelado de dos estrategias de comparación:
      * "treat_all": NB_all = prevalencia − (1 − prevalencia) × θ/(1−θ)
      * "treat_none": NB_none = 0
  - Curva NB(θ) evaluada en una grilla de umbrales
  - Rango útil: θ donde NB_model > max(NB_all, NB_none)
  - Decisión canónica:
      use_model              — el modelo domina en el rango dado
      do_not_use_model       — otra estrategia es superior
      restrict_to_threshold_range — el modelo es útil solo en parte del rango

Inputs esperados:
  - tp_rate:    Tasa de verdaderos positivos (sensibilidad) ∈ (0,1)
  - fp_rate:    Tasa de falsos positivos (1 − especificidad) ∈ (0,1)
  - prevalence: Prevalencia de la enfermedad ∈ (0,1)
  - theta:      Umbral clínico de referencia ∈ (0,1)
  - theta_range: [min, max] rango clínicamente relevante (opcional)

Nota: Este módulo trabaja con un modelo calibrado implícito (TP/FP fijos).
Para usar con curvas empíricas, se necesitaría pasar la curva completa.

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from hipocrates.utils.types import Action, ClinicalOutput


def net_benefit(
    tp_rate: float,
    fp_rate: float,
    prevalence: float,
    theta: float,
) -> float:
    """
    Beneficio Neto del modelo en el umbral θ.

    NB(θ) = (TP/N) − (FP/N) × (θ / (1 − θ))
           = sens × prev − (1 − spec) × (1 − prev) × (θ / (1 − θ))

    Args:
        tp_rate:    Sensibilidad (TPR).
        fp_rate:    1 − especificidad (FPR).
        prevalence: Prevalencia de la condición.
        theta:      Umbral de decisión ∈ (0, 1) estricto.

    Raises:
        ValueError: Si theta = 0 o theta = 1 (denominador inválido).
    """
    if not (0.0 < theta < 1.0):
        raise ValueError(f"theta debe estar en (0,1) estricto, recibido: {theta}")
    weight = theta / (1.0 - theta)
    nb_model = tp_rate * prevalence - fp_rate * (1.0 - prevalence) * weight
    return nb_model


def net_benefit_treat_all(prevalence: float, theta: float) -> float:
    """
    NB de la estrategia 'tratar a todos':
    NB_all(θ) = prev − (1 − prev) × θ/(1−θ)
    """
    if not (0.0 < theta < 1.0):
        raise ValueError(f"theta debe estar en (0,1) estricto, recibido: {theta}")
    weight = theta / (1.0 - theta)
    return prevalence - (1.0 - prevalence) * weight


def run_dca(
    tp_rate: float,
    fp_rate: float,
    prevalence: float,
    theta: float,
    theta_range: Optional[list[float]] = None,
    n_points: int = 50,
) -> ClinicalOutput:
    """
    Ejecuta DCA y determina la estrategia óptima.

    Args:
        tp_rate:     Sensibilidad del modelo ∈ (0,1).
        fp_rate:     FPR del modelo ∈ (0,1).
        prevalence:  Prevalencia ∈ (0,1).
        theta:       Umbral clínico de referencia.
        theta_range: [lo, hi] del rango a evaluar. Default [0.05, 0.5].
        n_points:    Puntos en la grilla de la curva.

    Returns:
        ClinicalOutput con curva NB, rango útil y decisión.
    """
    # Precondiciones
    for name, val in [("tp_rate", tp_rate), ("fp_rate", fp_rate), ("prevalence", prevalence)]:
        if not (0.0 < val < 1.0):
            raise ValueError(f"'{name}' debe estar en (0,1) estricto, recibido: {val}")

    if theta_range is None:
        theta_range = [0.05, 0.50]

    lo, hi = theta_range[0], theta_range[1]
    if not (0 < lo < hi < 1):
        raise ValueError(f"theta_range inválido: {theta_range}")

    # Grilla de umbrales
    step = (hi - lo) / max(n_points - 1, 1)
    thetas = [lo + i * step for i in range(n_points)]

    # Curvas NB
    curve_model: list[dict[str, float]] = []
    curve_treat_all: list[dict[str, float]] = []
    useful_thetas: list[float] = []

    for t in thetas:
        nb_m = net_benefit(tp_rate, fp_rate, prevalence, t)
        nb_a = net_benefit_treat_all(prevalence, t)
        nb_n = 0.0  # treat_none

        curve_model.append({"theta": round(t, 4), "NB": round(nb_m, 6)})
        curve_treat_all.append({"theta": round(t, 4), "NB": round(nb_a, 6)})

        if nb_m > max(nb_a, nb_n):
            useful_thetas.append(round(t, 4))

    # NB en el umbral de referencia
    nb_at_theta = net_benefit(tp_rate, fp_rate, prevalence, theta)
    nb_all_at_theta = net_benefit_treat_all(prevalence, theta)

    # Decisión
    model_dominates_at_theta = nb_at_theta > max(nb_all_at_theta, 0.0)

    if not useful_thetas:
        action = Action.DO_NOT_USE_MODEL
        decision_explain = "El modelo no supera ninguna estrategia alternativa en el rango dado."
    elif len(useful_thetas) == len(thetas):
        action = Action.USE_MODEL
        decision_explain = "El modelo domina en todo el rango clínicamente relevante."
    else:
        action = Action.RESTRICT_TO_THRESHOLD_RANGE
        decision_explain = (
            f"El modelo es útil en θ ∈ [{min(useful_thetas):.3f}, {max(useful_thetas):.3f}] "
            f"(subconjunto del rango evaluado)."
        )

    explain = (
        f"DCA — Modelo con sens={tp_rate:.3f}, FPR={fp_rate:.3f}, prevalencia={prevalence:.3f}. "
        f"NB(θ={theta:.3f}) = {nb_at_theta:.4f} | NB_all = {nb_all_at_theta:.4f}. "
        f"{'Modelo superior en θ de referencia.' if model_dominates_at_theta else 'Modelo NO superior en θ de referencia.'} "
        f"{decision_explain}"
    )

    return ClinicalOutput(
        result={
            "nb_at_theta": round(nb_at_theta, 6),
            "nb_treat_all_at_theta": round(nb_all_at_theta, 6),
            "nb_treat_none": 0.0,
            "model_dominates_at_reference_theta": model_dominates_at_theta,
            "useful_theta_range": (
                [min(useful_thetas), max(useful_thetas)] if useful_thetas else None
            ),
            "n_useful_thetas": len(useful_thetas),
            "curve_model": curve_model,
            "curve_treat_all": curve_treat_all,
            "theta_reference": theta,
            "theta_range_evaluated": theta_range,
        },
        action=action,
        p=None,
        U=None,
        NB={"theta": theta, "value": round(nb_at_theta, 6)},
        units_ok=True,
        explain=explain,
        ci=None,
    )


def run(clinical_input_dict: dict[str, Any]) -> ClinicalOutput:
    """
    Interfaz estándar del módulo DCA.

    Campos en inputs:
      - tp_rate:     float, sensibilidad
      - fp_rate:     float, 1 − especificidad
      - prevalence:  float
      - theta:       float, umbral de referencia
      - theta_range: [lo, hi] opcional
    """
    inp = clinical_input_dict["inputs"]
    return run_dca(
        tp_rate=float(inp["tp_rate"]),
        fp_rate=float(inp["fp_rate"]),
        prevalence=float(inp["prevalence"]),
        theta=float(inp["theta"]),
        theta_range=inp.get("theta_range"),
    )
