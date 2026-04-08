"""
types.py — Tipos compartidos del sistema Hipócrates.

Define las estructuras de entrada/salida homogéneas (contrato SMNC-5+).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ClinicalInput:
    """Payload de entrada clínica validado."""
    patient_id: str
    module: str
    inputs: dict[str, Any]
    constraints: dict[str, Any]
    version: str


@dataclass
class ClinicalOutput:
    """
    Salida homogénea del sistema Hipócrates (contrato SMNC-5+).

    Campos obligatorios:
      result  — resultado específico del módulo (dict libre)
      action  — decisión recomendada (string canónico)
      p       — probabilidad posterior principal (float ∈ [0,1] o None)
      U       — utilidad esperada (float o None)
      NB      — beneficio neto DCA (dict con theta y value, o None)
      units_ok— todas las unidades y dominios superaron el gate (bool)
      explain — texto explicativo de la salida
      ci      — intervalos de confianza (dict o None)
    """
    result: dict[str, Any]
    action: str
    p: Optional[float]
    U: Optional[float]
    NB: Optional[dict[str, Any]]
    units_ok: bool
    explain: str
    ci: Optional[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "action": self.action,
            "p": self.p,
            "U": self.U,
            "NB": self.NB,
            "units_ok": self.units_ok,
            "explain": self.explain,
            "ci": self.ci,
        }


# Acciones canónicas del sistema
class Action:
    START_TREATMENT = "start_treatment"
    DISCARD_DIAGNOSIS = "discard_diagnosis"
    OBTAIN_TEST = "obtain_test"
    OBSERVE = "observe"
    USE_MODEL = "use_model"
    DO_NOT_USE_MODEL = "do_not_use_model"
    RESTRICT_TO_THRESHOLD_RANGE = "restrict_to_threshold_range"
    REVIEW_DOSING = "review_dosing"   # PK_TDM: dosis fuera de ventana terapéutica
    ERROR = "error"
    BLOCKED = "blocked"
