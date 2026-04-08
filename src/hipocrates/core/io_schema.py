"""
io_schema.py — Clinical_IO_Schema

Valida el payload de entrada clínica y construye ClinicalInput.
Contrato SMNC-5+: toda solicitud debe contener patient_id, module,
inputs, constraints, version.

No hace inferencia clínica. Solo valida estructura.
"""

from __future__ import annotations
from typing import Any

from hipocrates.utils.types import ClinicalInput

# Claves obligatorias en el payload de entrada
REQUIRED_KEYS: list[str] = ["patient_id", "module", "inputs", "constraints", "version"]

# Módulos reconocidos en este MVP
VALID_MODULES: set[str] = {
    "bayes_sprt",
    "abg_hh_stewart",
    "dca",
    "pk_tdm",
    "sepsis_protocol",
}

# Versión de schema compatible
SCHEMA_VERSION_PREFIX = "SMNC-5+"


class SchemaValidationError(Exception):
    """Error de validación del schema de entrada."""


def validate_input(payload: dict[str, Any]) -> ClinicalInput:
    """
    Valida el payload de entrada clínica.

    Args:
        payload: Diccionario con el payload JSON de entrada.

    Returns:
        ClinicalInput validado.

    Raises:
        SchemaValidationError: Si falta alguna clave obligatoria o el valor
                               es inválido.
    """
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            f"El payload debe ser un dict, recibido: {type(payload).__name__}"
        )

    # 1. Verificar claves obligatorias
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise SchemaValidationError(
            f"Faltan claves obligatorias en el payload: {missing}"
        )

    # 2. patient_id debe ser string no vacío
    patient_id = payload["patient_id"]
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise SchemaValidationError(
            f"'patient_id' debe ser un string no vacío, recibido: {patient_id!r}"
        )

    # 3. module debe ser string y estar en los módulos válidos
    module = payload["module"]
    if not isinstance(module, str):
        raise SchemaValidationError(
            f"'module' debe ser un string, recibido: {type(module).__name__}"
        )
    if module not in VALID_MODULES:
        raise SchemaValidationError(
            f"Módulo no reconocido: '{module}'. Módulos disponibles en este MVP: {sorted(VALID_MODULES)}"
        )

    # 4. inputs debe ser dict no vacío
    inputs = payload["inputs"]
    if not isinstance(inputs, dict):
        raise SchemaValidationError(
            f"'inputs' debe ser un dict, recibido: {type(inputs).__name__}"
        )
    if not inputs:
        raise SchemaValidationError("'inputs' no puede ser un dict vacío.")

    # 5. constraints debe ser dict (puede estar vacío)
    constraints = payload["constraints"]
    if not isinstance(constraints, dict):
        raise SchemaValidationError(
            f"'constraints' debe ser un dict, recibido: {type(constraints).__name__}"
        )

    # 6. version debe comenzar con el prefijo esperado
    version = payload["version"]
    if not isinstance(version, str):
        raise SchemaValidationError(
            f"'version' debe ser un string, recibido: {type(version).__name__}"
        )
    if not version.startswith(SCHEMA_VERSION_PREFIX):
        raise SchemaValidationError(
            f"'version' debe comenzar con '{SCHEMA_VERSION_PREFIX}', recibido: {version!r}"
        )

    return ClinicalInput(
        patient_id=patient_id.strip(),
        module=module,
        inputs=inputs,
        constraints=constraints,
        version=version,
    )
