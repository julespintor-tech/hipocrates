"""
audit.py — Audit_Log_Provenance

Registra cada solicitud procesada por el orquestador.
Persistencia: JSONL (una línea JSON por entrada).

Cada registro incluye:
  - request_id    UUID v4
  - patient_id
  - module
  - inputs        copia del payload de entrada
  - version       del schema
  - timestamp     ISO 8601 UTC

  - sha256_input  Hash SHA-256 de {patient_id, module, inputs, version}
                  SIN timestamp. Determinista: el mismo payload siempre
                  produce el mismo hash. Permite detectar duplicados exactos
                  y verificar integridad del input independientemente de cuándo
                  se procesó.

  - sha256_event  Hash SHA-256 del evento completo: {patient_id, module,
                  inputs, version, timestamp, request_id}. Incluye timestamp
                  y request_id, por lo que es único por ejecución. Garantiza
                  integridad del registro completo tal como fue emitido.

No requiere base de datos. El archivo de log es independiente por sesión.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Directorio por defecto para logs de auditoría
# audit.py está en src/hipocrates/core/ → parents[3] = raíz del proyecto
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "outputs"
_DEFAULT_LOG_FILE = _DEFAULT_LOG_DIR / "audit_log.jsonl"


def _canonical_json(data: dict[str, Any]) -> str:
    """Serializa el dict de forma canónica (claves ordenadas, sin espacios)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(
    patient_id: str,
    module: str,
    inputs: dict[str, Any],
    version: str,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """
    Crea y persiste un registro de auditoría.

    Args:
        patient_id: Identificador del paciente.
        module:     Nombre del módulo ejecutado.
        inputs:     Inputs originales del payload.
        version:    Versión del schema usada.
        log_path:   Ruta al archivo JSONL. Si None, usa el default.

    Returns:
        El registro de auditoría como dict.
    """
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # sha256_input: hash determinista del contenido clínico, SIN timestamp.
    # Mismo payload → mismo hash, independientemente de cuándo se ejecutó.
    input_canonical = _canonical_json({
        "patient_id": patient_id,
        "module": module,
        "inputs": inputs,
        "version": version,
    })
    sha256_input = _sha256(input_canonical)

    # sha256_event: hash del evento completo incluyendo timestamp y request_id.
    # Único por ejecución. Garantiza integridad del registro tal como fue emitido.
    event_canonical = _canonical_json({
        "patient_id": patient_id,
        "module": module,
        "inputs": inputs,
        "version": version,
        "timestamp": timestamp,
        "request_id": request_id,
    })
    sha256_event = _sha256(event_canonical)

    audit_record: dict[str, Any] = {
        "request_id": request_id,
        "patient_id": patient_id,
        "module": module,
        "inputs": inputs,
        "version": version,
        "timestamp": timestamp,
        "sha256_input": sha256_input,
        "sha256_event": sha256_event,
    }

    _persist(audit_record, log_path)
    return audit_record


def _persist(record_dict: dict[str, Any], log_path: Path | None) -> None:
    """
    Escribe el registro en el archivo JSONL.
    Crea el directorio si no existe.
    """
    path = log_path or _DEFAULT_LOG_FILE
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as fh:
        fh.write(_canonical_json(record_dict) + "\n")


def read_log(log_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Lee y retorna todos los registros del log de auditoría.

    Returns:
        Lista de dicts con los registros, en orden cronológico.
    """
    path = log_path or _DEFAULT_LOG_FILE
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
