"""
units_gate.py — Units_Validity_Gate

Gate de validación dimensional y de dominio (SMNC-5+).
Bloquea ejecución si cualquier variable viola su dominio declarado.

Chequeos implementados:
  - Probabilidades en (0, 1) estricto
  - Concentraciones ≥ 0
  - Ausencia de NaN / inf en cualquier campo numérico
  - Reglas de dominio explícitas según módulo

INVARIANTE: units_ok=True ⟹ ningún campo viola su dominio.
"""

from __future__ import annotations
import math
from typing import Any

from hipocrates.utils.types import ClinicalInput


class UnitsGateError(Exception):
    """Violación de dominio detectada por el gate de validación."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            "Units gate bloqueó la ejecución. Violaciones: " + "; ".join(violations)
        )


def _is_finite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _check_generic(inputs: dict[str, Any]) -> list[str]:
    """
    Chequeos genéricos aplicables a cualquier módulo:
      - Ningún valor numérico puede ser NaN o inf.
    """
    violations: list[str] = []
    for key, value in inputs.items():
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                violations.append(
                    f"Campo '{key}' contiene valor no finito: {value}"
                )
    return violations


def _check_probabilities(inputs: dict[str, Any], prob_keys: list[str]) -> list[str]:
    """
    Verifica que las claves indicadas sean probabilidades en (0, 1) estricto.
    """
    violations: list[str] = []
    for key in prob_keys:
        if key in inputs:
            v = inputs[key]
            try:
                vf = float(v)
                if not (0.0 < vf < 1.0):
                    violations.append(
                        f"'{key}' = {v} fuera del dominio de probabilidad (0, 1) estricto."
                    )
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")
    return violations


def _check_non_negative(inputs: dict[str, Any], conc_keys: list[str]) -> list[str]:
    """
    Verifica que las claves indicadas sean ≥ 0 (concentraciones, volúmenes, etc.).
    """
    violations: list[str] = []
    for key in conc_keys:
        if key in inputs:
            v = inputs[key]
            try:
                vf = float(v)
                if vf < 0.0:
                    violations.append(
                        f"'{key}' = {v} es negativo. Las concentraciones deben ser ≥ 0."
                    )
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")
    return violations


# Reglas de dominio específicas por módulo
_MODULE_PROB_KEYS: dict[str, list[str]] = {
    "bayes_sprt": ["p0"],
    "dca": [],
    "abg_hh_stewart": [],
    "pk_tdm": [],
}

_MODULE_NONNEG_KEYS: dict[str, list[str]] = {
    "bayes_sprt": [],
    "dca": [],
    "abg_hh_stewart": ["paco2", "hco3", "na", "k", "cl", "albumin_g_dl", "phosphate_mg_dl"],
    "pk_tdm": ["time_h", "c0_mg_L"],
    # sepsis_protocol: campos ≥ 0 (opcionales también se validan si presentes)
    "sepsis_protocol": [
        "lactate_mmol_L",
        "urine_output_ml_kg_h",
        "creatinine_mg_dL",
        "bilirubin_mg_dL",
    ],
}

# Reglas de rango específico por módulo: {key: (min_inclusive, max_inclusive)}
_MODULE_RANGE_RULES: dict[str, dict[str, tuple[float, float]]] = {
    "abg_hh_stewart": {
        "ph": (6.5, 8.0),
        "paco2": (5.0, 120.0),
        "hco3": (1.0, 60.0),
    },
    "bayes_sprt": {},
    "dca": {
        "theta": (0.0, 1.0),
    },
    "pk_tdm": {},
}

# Claves que deben ser estrictamente positivas por módulo
_MODULE_POSITIVE_KEYS: dict[str, list[str]] = {
    "pk_tdm": [
        "dose_mg", "vd_L", "cl_L_h", "rate_mg_h",
        "tau_h", "ka_h", "km_mg_L", "vmax_mg_day",
        "dose_guess_mg_day", "target_css_mg_L",
        "standard_dose_mg", "clcr_patient_mL_min",
    ],
    "bayes_sprt": [],
    "dca": [],
    "abg_hh_stewart": [],
    "sepsis_protocol": [],  # validaciones específicas en _check_sepsis_specific
}


def _check_sepsis_specific(inputs: dict[str, Any]) -> list[str]:
    """
    Validaciones específicas para sepsis_protocol.
    Bloquea valores claramente inválidos en los parámetros fisiológicos.

    Reglas:
      - rr > 0                          (frecuencia respiratoria)
      - sbp > 0                         (presión sistólica)
      - map_mmHg > 0                    (presión arterial media)
      - lactate_mmol_L ≥ 0             (lactato, 0 es válido)
      - urine_output_ml_kg_h ≥ 0       (si presente)
      - creatinine_mg_dL ≥ 0           (si presente)
      - bilirubin_mg_dL ≥ 0            (si presente)
      - platelets_k_uL > 0             (si presente)
      - pao2_fio2 > 0                  (si presente)
      - booleanos deben ser bool/int
    """
    violations: list[str] = []

    # Campos requeridos estrictamente positivos
    for key in ("rr", "sbp", "map_mmHg"):
        if key in inputs:
            v = inputs[key]
            try:
                vf = float(v)
                if not math.isfinite(vf):
                    violations.append(f"'{key}' contiene valor no finito: {v}")
                elif vf <= 0:
                    violations.append(f"'{key}' debe ser > 0, recibido: {v}")
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")

    # platelets_k_uL y pao2_fio2: si presentes, deben ser > 0
    for key in ("platelets_k_uL", "pao2_fio2"):
        v = inputs.get(key)
        if v is not None:
            try:
                vf = float(v)
                if not math.isfinite(vf):
                    violations.append(f"'{key}' contiene valor no finito: {v}")
                elif vf <= 0:
                    violations.append(f"'{key}' debe ser > 0, recibido: {v}")
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")

    # Booleanos: deben ser bool o int (0/1)
    for key in ("suspected_infection", "mental_status_altered", "vasopressor"):
        if key in inputs:
            v = inputs[key]
            if not isinstance(v, (bool, int)):
                violations.append(
                    f"'{key}' debe ser bool (true/false), recibido: {v!r}"
                )

    return violations


def _check_pk_specific(inputs: dict[str, Any]) -> list[str]:
    """
    Validaciones específicas para pk_tdm que no encajan en los chequeos genéricos.
    Cubre modos v1 y v2 (cockcroft_gault, target_dosing_renal, tdm_bayes_map).

    Verifica:
      - Campos de valor positivo (solo si están presentes)
      - Biodisponibilidad F en (0, 1]
      - Ventanas terapéuticas bien formadas
      - Campos v2: age, weight_kg, serum_creatinine_mg_dL > 0
      - observed_concentrations: lista de dicts {time_h ≥ 0, conc_mg_L ≥ 0}
      - prior SDs > 0
      - Ningún valor numérico es NaN / inf (complementa _check_generic)
    """
    violations: list[str] = []

    # Claves que deben ser > 0 (solo si presentes) — v1 + v2
    positive_keys = _MODULE_POSITIVE_KEYS.get("pk_tdm", [])
    # Añadir claves v2 al conjunto
    positive_keys_v2 = [
        "age", "weight_kg", "serum_creatinine_mg_dL",
        "base_cl_L_h", "drug_clcr_reference_mL_min",
        "prior_cl_mean_L_h", "prior_cl_sd_L_h",
        "prior_vd_mean_L", "prior_vd_sd_L",
        "sigma_obs_mg_L",
    ]
    all_positive_keys = list(positive_keys) + positive_keys_v2

    for key in all_positive_keys:
        if key in inputs:
            v = inputs[key]
            try:
                vf = float(v)
                if not math.isfinite(vf):
                    violations.append(f"'{key}' contiene valor no finito: {v}")
                elif vf <= 0.0:
                    violations.append(f"'{key}' debe ser > 0, recibido: {v}")
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")

    # Biodisponibilidad F en (0, 1]
    if "F" in inputs:
        v = inputs["F"]
        try:
            vf = float(v)
            if not (0.0 < vf <= 1.0):
                violations.append(
                    f"'F' (biodisponibilidad) debe estar en (0, 1], recibido: {v}"
                )
        except (TypeError, ValueError):
            violations.append(f"'F' no es un número válido: {v!r}")

    # Ventana terapéutica therapeutic_window
    for tw_key in ("therapeutic_window", "target_range_mg_L"):
        if tw_key in inputs:
            tw = inputs[tw_key]
            try:
                if not (isinstance(tw, (list, tuple)) and len(tw) == 2):
                    violations.append(
                        f"'{tw_key}' debe ser [min, max], recibido: {tw!r}"
                    )
                else:
                    lo, hi = float(tw[0]), float(tw[1])
                    if lo < 0 or hi < 0:
                        violations.append(
                            f"'{tw_key}' no puede contener valores negativos: {tw!r}"
                        )
                    elif lo >= hi:
                        violations.append(
                            f"'{tw_key}' debe tener min < max, recibido: {tw!r}"
                        )
            except (TypeError, ValueError):
                violations.append(f"'{tw_key}' contiene valores no numéricos: {tw!r}")

    # v2: observed_concentrations — validación estructural
    if "observed_concentrations" in inputs:
        obs = inputs["observed_concentrations"]
        if not isinstance(obs, list):
            violations.append(
                f"'observed_concentrations' debe ser una lista, recibido: {type(obs).__name__}"
            )
        elif len(obs) == 0:
            violations.append("'observed_concentrations' no puede ser una lista vacía.")
        else:
            for i, o in enumerate(obs):
                if not isinstance(o, dict):
                    violations.append(
                        f"'observed_concentrations[{i}]' debe ser dict {{time_h, conc_mg_L}}, "
                        f"recibido: {type(o).__name__}"
                    )
                    continue
                for sub_key in ("time_h", "conc_mg_L"):
                    if sub_key not in o:
                        violations.append(
                            f"'observed_concentrations[{i}]' falta clave requerida: '{sub_key}'"
                        )
                    else:
                        try:
                            sv = float(o[sub_key])
                            if not math.isfinite(sv):
                                violations.append(
                                    f"'observed_concentrations[{i}].{sub_key}' no finito: {sv}"
                                )
                            elif sv < 0:
                                violations.append(
                                    f"'observed_concentrations[{i}].{sub_key}' debe ser ≥ 0, "
                                    f"recibido: {sv}"
                                )
                        except (TypeError, ValueError):
                            violations.append(
                                f"'observed_concentrations[{i}].{sub_key}' no es numérico: "
                                f"{o[sub_key]!r}"
                            )

    return violations


def run_gate(clinical_input: ClinicalInput) -> None:
    """
    Ejecuta todos los chequeos de dominio sobre el ClinicalInput.

    Raises:
        UnitsGateError: con lista de todas las violaciones encontradas.
    """
    violations: list[str] = []
    inputs = clinical_input.inputs
    module = clinical_input.module

    # 1. Chequeos genéricos (NaN / inf)
    violations.extend(_check_generic(inputs))

    # 2. Chequeos de probabilidades para este módulo
    prob_keys = _MODULE_PROB_KEYS.get(module, [])
    violations.extend(_check_probabilities(inputs, prob_keys))

    # 3. Chequeos de no-negatividad para este módulo
    nonneg_keys = _MODULE_NONNEG_KEYS.get(module, [])
    violations.extend(_check_non_negative(inputs, nonneg_keys))

    # 4. Chequeos de rango específico por módulo
    range_rules = _MODULE_RANGE_RULES.get(module, {})
    for key, (lo, hi) in range_rules.items():
        if key in inputs:
            v = inputs[key]
            try:
                vf = float(v)
                if not (lo <= vf <= hi):
                    violations.append(
                        f"'{key}' = {v} fuera del rango permitido [{lo}, {hi}]."
                    )
            except (TypeError, ValueError):
                violations.append(f"'{key}' no es un número válido: {v!r}")

    # 5. Chequeos específicos de pk_tdm
    if module == "pk_tdm":
        violations.extend(_check_pk_specific(inputs))

    # 6. Chequeos específicos de sepsis_protocol
    if module == "sepsis_protocol":
        violations.extend(_check_sepsis_specific(inputs))

    if violations:
        raise UnitsGateError(violations)
