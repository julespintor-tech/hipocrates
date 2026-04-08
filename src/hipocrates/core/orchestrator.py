"""
orchestrator.py — Hipocrates_Orchestrator (mínimo MVP)

Orquesta el pipeline completo para cada solicitud:
  1. Valida schema de entrada (Clinical_IO_Schema)
  2. Ejecuta Units_Validity_Gate
  3. Llama al módulo computacional correspondiente
  4. Registra auditoría (Audit_Log_Provenance)
  5. Retorna ClinicalOutput homogéneo

Módulos disponibles en este snapshot:
  - bayes_sprt         (Bayes_SPRT_Engine)
  - abg_hh_stewart     (ABG_HH_Stewart_Engine)
  - dca                (DCA_Utility_Module)
  - pk_tdm             (PK_TDM_Core v2.0)
  - sepsis_protocol    (Sepsis_Protocol_Engine)

Contrato de salida: siempre retorna un dict serializable con la estructura
definida en ClinicalOutput. En caso de error, retorna action="error" o
action="blocked" con explain descriptivo.

ADVERTENCIA: Motor de apoyo computacional. No usar en decisiones clínicas autónomas.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Optional

from hipocrates.core import audit
from hipocrates.core.io_schema import SchemaValidationError, validate_input
from hipocrates.core.units_gate import UnitsGateError, run_gate
from hipocrates.modules import bayes_sprt, abg_hh_stewart, dca, pk_tdm, sepsis_protocol
from hipocrates.utils.types import Action, ClinicalOutput

# Registro de módulos disponibles
_MODULE_REGISTRY: dict[str, Any] = {
    "bayes_sprt": bayes_sprt,
    "abg_hh_stewart": abg_hh_stewart,
    "dca": dca,
    "pk_tdm": pk_tdm,
    "sepsis_protocol": sepsis_protocol,
}


def _error_output(message: str, action: str = Action.ERROR) -> dict[str, Any]:
    """Genera un output de error homogéneo."""
    return ClinicalOutput(
        result={"error": message},
        action=action,
        p=None,
        U=None,
        NB=None,
        units_ok=False,
        explain=message,
        ci=None,
    ).to_dict()


def run(
    payload: dict[str, Any],
    log_path: Optional[Path] = None,
    skip_units_gate: bool = False,
) -> dict[str, Any]:
    """
    Punto de entrada principal del orquestador.

    Args:
        payload:         Payload JSON clínico completo.
        log_path:        Ruta al archivo JSONL de auditoría. None = default.
        skip_units_gate: Solo para testing interno. Nunca en producción.

    Returns:
        Dict con la salida homogénea (ClinicalOutput serializado).
    """
    # ──────────────────────────────────────────────────────────────────────
    # FASE 1: Validación de schema
    # ──────────────────────────────────────────────────────────────────────
    try:
        clinical_input = validate_input(payload)
    except SchemaValidationError as exc:
        return _error_output(f"[SchemaError] {exc}", action=Action.ERROR)
    except Exception as exc:
        return _error_output(f"[SchemaError inesperado] {exc}", action=Action.ERROR)

    # ──────────────────────────────────────────────────────────────────────
    # FASE 2: Units Validity Gate
    # ──────────────────────────────────────────────────────────────────────
    if not skip_units_gate:
        try:
            run_gate(clinical_input)
            units_ok = True
        except UnitsGateError as exc:
            # El gate bloqueó — registrar auditoría y capturar request_id
            # para incluirlo en la respuesta bloqueada (trazabilidad del cliente).
            blocked_request_id: Optional[str] = None
            try:
                blocked_audit = audit.record(
                    patient_id=clinical_input.patient_id,
                    module=clinical_input.module,
                    inputs=clinical_input.inputs,
                    version=clinical_input.version,
                    log_path=log_path,
                )
                blocked_request_id = blocked_audit["request_id"]
            except Exception:
                pass  # Auditoría falló — no inventar request_id; seguir sin él

            blocked_out = ClinicalOutput(
                result={"gate_violations": exc.violations},
                action=Action.BLOCKED,
                p=None,
                U=None,
                NB=None,
                units_ok=False,
                explain=f"[UnitsGate] Ejecución bloqueada. {exc}",
                ci=None,
            ).to_dict()
            if blocked_request_id is not None:
                blocked_out["request_id"] = blocked_request_id
            return blocked_out
    else:
        units_ok = True

    # ──────────────────────────────────────────────────────────────────────
    # FASE 3: Ejecución del módulo
    # ──────────────────────────────────────────────────────────────────────
    module_name = clinical_input.module
    module = _MODULE_REGISTRY.get(module_name)
    if module is None:
        return _error_output(
            f"Módulo '{module_name}' no registrado en el orquestador.",
            action=Action.ERROR,
        )

    try:
        # Pasamos el payload como dict (el módulo accede a inputs internamente)
        output: ClinicalOutput = module.run(
            {
                "patient_id": clinical_input.patient_id,
                "module": clinical_input.module,
                "inputs": clinical_input.inputs,
                "constraints": clinical_input.constraints,
                "version": clinical_input.version,
            }
        )
        output.units_ok = units_ok
    except Exception as exc:
        tb = traceback.format_exc()
        return _error_output(
            f"[ModuleError] Error en módulo '{module_name}': {exc}\n{tb}",
            action=Action.ERROR,
        )

    # ──────────────────────────────────────────────────────────────────────
    # FASE 4: Registro de auditoría
    # ──────────────────────────────────────────────────────────────────────
    try:
        audit_record = audit.record(
            patient_id=clinical_input.patient_id,
            module=clinical_input.module,
            inputs=clinical_input.inputs,
            version=clinical_input.version,
            log_path=log_path,
        )
        # Agregar request_id al resultado para trazabilidad
        result_dict = output.to_dict()
        result_dict["request_id"] = audit_record["request_id"]
    except Exception as exc:
        # La auditoría falla — el resultado es válido, pero se advierte
        result_dict = output.to_dict()
        result_dict["audit_warning"] = f"Auditoría no registrada: {exc}"

    return result_dict
