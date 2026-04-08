"""
bayes_sprt.py — Bayes_SPRT_Engine

Motor de actualización diagnóstica secuencial (SMNC-5+, §3.1 + §6.1 + §6.3).

Implementa:
  - Odds pretest desde p0
  - Actualización secuencial por LR con PARADA TEMPRANA (SPRT de Wald real):
      en cada paso, si p ≥ θ_T → start_treatment (para inmediatamente)
                   si p ≤ θ_A → discard_diagnosis (para inmediatamente)
      Los tests restantes NO se procesan una vez cruzado un umbral.
  - Posterior p en el paso de parada
  - Trazabilidad: pasos aplicados + tests_skipped (los no procesados)
  - Decisión canónica: start_treatment | discard_diagnosis | obtain_test | observe

Fórmulas (SMNC-5+):
  O_0  = p0 / (1 − p0)
  O_k  = O_{k-1} × LR_k      ← actualización en cada paso
  p_k  = O_k / (1 + O_k)
  PARAR si p_k ≥ θ_T  o  p_k ≤ θ_A   ← chequeo DENTRO del loop

Limitaciones explícitas:
  - Los LR se asumen independientes entre sí (sin DAG). Si hay dependencia
    conocida entre pruebas, se debe usar LR condicional (no implementado aún).
  - No es un reemplazo de criterio clínico.

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from hipocrates.utils.math_utils import prob_to_odds, odds_to_prob
from hipocrates.utils.types import Action, ClinicalOutput


@dataclass
class BayesTrace:
    """Traza de un paso de actualización bayesiana."""
    step: int
    test_name: str
    lr_applied: float
    odds_before: float
    odds_after: float
    p_after: float
    sprt_stop: bool   # True si este paso cruzó un umbral y detuvo el proceso


def run_bayes_sprt(
    p0: float,
    tests: list[dict[str, Any]],
    theta_T: float,
    theta_A: float,
) -> ClinicalOutput:
    """
    Ejecuta SPRT de Wald con parada temprana real.

    La actualización es secuencial: después de incorporar cada LR se evalúan
    los umbrales. Si se cruza θ_T o θ_A, el loop para inmediatamente y los
    tests restantes quedan registrados en 'tests_skipped'.

    Args:
        p0:      Probabilidad pretest ∈ (0, 1) estricto.
        tests:   Lista de dicts con claves 'name', 'lr', 'result'.
                 LR debe ser > 0 (por invariante del sistema).
        theta_T: Umbral de tratamiento — si p_k ≥ theta_T → start_treatment.
        theta_A: Umbral de descarte   — si p_k ≤ theta_A → discard_diagnosis.
                 Debe cumplirse 0 < theta_A < theta_T < 1.

    Returns:
        ClinicalOutput con la decisión, posterior en el paso de parada,
        traza de pasos aplicados, y lista de tests no procesados.

    Raises:
        ValueError: Si los argumentos violan las precondiciones.
    """
    # --- Precondiciones ---
    if not (0.0 < p0 < 1.0):
        raise ValueError(f"p0 debe estar en (0,1) estricto, recibido: {p0}")
    if not (0.0 < theta_A < theta_T < 1.0):
        raise ValueError(
            f"Debe cumplirse 0 < theta_A ({theta_A}) < theta_T ({theta_T}) < 1"
        )

    # --- Inicialización ---
    odds = prob_to_odds(p0)
    trace: list[BayesTrace] = []
    action: str = Action.OBSERVE   # acción por defecto si no se cruza ningún umbral
    sprt_stopped_at: Optional[int] = None

    # --- SPRT: actualización secuencial con parada temprana ---
    for step, t in enumerate(tests, start=1):
        lr = float(t["lr"])
        if lr <= 0:
            raise ValueError(
                f"LR debe ser > 0 para la prueba '{t['name']}', recibido: {lr}"
            )

        odds_before = odds
        odds = odds * lr
        p_step = odds_to_prob(odds)

        # Chequeo de umbral DENTRO del loop (SPRT real)
        crossed = p_step >= theta_T or p_step <= theta_A
        trace.append(
            BayesTrace(
                step=step,
                test_name=t["name"],
                lr_applied=lr,
                odds_before=odds_before,
                odds_after=odds,
                p_after=p_step,
                sprt_stop=crossed,
            )
        )

        if crossed:
            sprt_stopped_at = step
            if p_step >= theta_T:
                action = Action.START_TREATMENT
            else:
                action = Action.DISCARD_DIAGNOSIS
            # Tests restantes: los que NO llegaron a procesarse
            tests_skipped = [t2["name"] for t2 in tests[step:]]
            break
    else:
        # Loop completo sin cruzar umbral
        tests_skipped = []
        if not tests:
            action = Action.OBSERVE
        else:
            action = Action.OBTAIN_TEST   # incertidumbre permanece — pedir más pruebas

    # --- Posterior en el punto de parada ---
    p_post = odds_to_prob(odds)
    n_applied = len(trace)

    # --- Explicación ---
    stop_msg = (
        f"SPRT paró en paso {sprt_stopped_at} de {len(tests)} posibles."
        if sprt_stopped_at is not None
        else f"SPRT completó los {len(tests)} tests sin cruzar umbral."
    )
    explain_parts = [
        f"Probabilidad pretest: {p0:.4f} (odds={prob_to_odds(p0):.4f}).",
        stop_msg,
        f"Tests aplicados: {n_applied}. Tests omitidos: {len(tests_skipped)}.",
        f"Probabilidad posterior: {p_post:.4f}.",
        f"Umbral tratar: {theta_T}, umbral descartar: {theta_A}.",
        f"Decisión: {action}.",
    ]
    if trace:
        explain_parts.append(
            "Traza: " + " → ".join(
                f"{tr.test_name}(LR={tr.lr_applied:.3f}→p={tr.p_after:.4f}"
                + ("★STOP" if tr.sprt_stop else "") + ")"
                for tr in trace
            )
        )

    # --- CI nominal (±0.05 logístico sobre posterior puntual) ---
    ci_lo = max(0.0001, p_post - 0.05)
    ci_hi = min(0.9999, p_post + 0.05)

    return ClinicalOutput(
        result={
            "p0": p0,
            "p_posterior": p_post,
            "odds_posterior": odds,
            "theta_T": theta_T,
            "theta_A": theta_A,
            "n_tests_provided": len(tests),
            "n_tests_applied": n_applied,
            "sprt_stopped_at_step": sprt_stopped_at,
            "tests_skipped": tests_skipped,
            "trace": [
                {
                    "step": tr.step,
                    "test": tr.test_name,
                    "lr": tr.lr_applied,
                    "odds_before": tr.odds_before,
                    "odds_after": tr.odds_after,
                    "p_after": tr.p_after,
                    "sprt_stop": tr.sprt_stop,
                }
                for tr in trace
            ],
        },
        action=action,
        p=p_post,
        U=None,
        NB=None,
        units_ok=True,
        explain=" ".join(explain_parts),
        ci={"95%_nominal": [round(ci_lo, 4), round(ci_hi, 4)]},
    )


def run(clinical_input_dict: dict[str, Any]) -> ClinicalOutput:
    """
    Interfaz estándar del módulo — recibe el dict de inputs ya validado.

    Campos esperados en inputs:
      - p0:       float, probabilidad pretest ∈ (0,1)
      - tests:    list of {name: str, lr: float, result: str}
      - theta_T:  float, umbral tratar (default 0.8)
      - theta_A:  float, umbral descartar (default 0.2)
    """
    inputs = clinical_input_dict["inputs"]
    p0 = float(inputs["p0"])
    tests = inputs.get("tests", [])
    theta_T = float(inputs.get("theta_T", 0.8))
    theta_A = float(inputs.get("theta_A", 0.2))

    return run_bayes_sprt(p0=p0, tests=tests, theta_T=theta_T, theta_A=theta_A)
