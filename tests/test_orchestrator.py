"""
test_orchestrator.py — Tests del Hipocrates_Orchestrator.

Cubre:
  - ejecución de módulo válido → salida homogénea
  - request_id generado en cada llamada
  - auditoría escrita (log JSONL)
  - gate bloquea con action="blocked" cuando hay violación
  - schema inválido devuelve action="error"
  - módulo desconocido devuelve action="error"
  - output tiene todas las claves del contrato SMNC-5+
"""

import json
import tempfile
from pathlib import Path
import pytest

from hipocrates.core import orchestrator
from hipocrates.utils.types import Action


# ── Fixtures ──────────────────────────────────────────────────────────────────

def bayes_payload() -> dict:
    return {
        "patient_id": "ORCH-TEST-001",
        "module": "bayes_sprt",
        "inputs": {
            "p0": 0.25,
            "tests": [{"name": "t1", "lr": 3.0, "result": "pos"}],
            "theta_T": 0.8,
            "theta_A": 0.05,
        },
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }

def abg_payload() -> dict:
    return {
        "patient_id": "ORCH-TEST-002",
        "module": "abg_hh_stewart",
        "inputs": {
            "ph": 7.40, "paco2": 40.0, "hco3": 24.0,
            "na": 140.0, "k": 4.0, "cl": 104.0,
        },
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }

def dca_payload() -> dict:
    return {
        "patient_id": "ORCH-TEST-003",
        "module": "dca",
        "inputs": {
            "tp_rate": 0.8, "fp_rate": 0.2,
            "prevalence": 0.3, "theta": 0.2,
        },
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }


# ── Contrato de salida ────────────────────────────────────────────────────────

class TestOutputContract:
    CONTRACT_KEYS = ["result", "action", "p", "U", "NB", "units_ok", "explain", "ci"]

    def test_bayes_output_has_all_keys(self):
        out = orchestrator.run(bayes_payload())
        for k in self.CONTRACT_KEYS:
            assert k in out, f"Clave faltante en salida: {k}"

    def test_abg_output_has_all_keys(self):
        out = orchestrator.run(abg_payload())
        for k in self.CONTRACT_KEYS:
            assert k in out

    def test_dca_output_has_all_keys(self):
        out = orchestrator.run(dca_payload())
        for k in self.CONTRACT_KEYS:
            assert k in out

    def test_units_ok_true_for_valid_inputs(self):
        out = orchestrator.run(bayes_payload())
        assert out["units_ok"] is True

    def test_action_is_nonempty_string(self):
        out = orchestrator.run(bayes_payload())
        assert isinstance(out["action"], str) and out["action"] != ""


# ── Request ID y auditoría ────────────────────────────────────────────────────

class TestAudit:
    def test_request_id_present(self):
        out = orchestrator.run(bayes_payload())
        assert "request_id" in out
        assert len(out["request_id"]) == 36  # UUID v4

    def test_request_id_unique(self):
        out1 = orchestrator.run(bayes_payload())
        out2 = orchestrator.run(bayes_payload())
        assert out1["request_id"] != out2["request_id"]

    def test_audit_log_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test_audit.jsonl"
            orchestrator.run(bayes_payload(), log_path=log_path)
            assert log_path.exists()
            records = log_path.read_text().strip().split("\n")
            assert len(records) == 1
            record = json.loads(records[0])
            assert record["patient_id"] == "ORCH-TEST-001"
            assert record["module"] == "bayes_sprt"
            assert "sha256_input" in record
            assert "sha256_event" in record
            assert "timestamp" in record
            assert "request_id" in record
            # sha256_input es determinista (no depende de timestamp)
            assert len(record["sha256_input"]) == 64
            assert len(record["sha256_event"]) == 64
            # los dos hashes deben ser distintos entre sí
            assert record["sha256_input"] != record["sha256_event"]

    def test_audit_accumulates_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test_audit.jsonl"
            for _ in range(3):
                orchestrator.run(bayes_payload(), log_path=log_path)
            records = log_path.read_text().strip().split("\n")
            assert len(records) == 3


# ── Gate bloquea ──────────────────────────────────────────────────────────────

class TestGateBlocking:
    def test_invalid_p0_blocked(self):
        payload = bayes_payload()
        payload["inputs"]["p0"] = 1.5  # inválido
        out = orchestrator.run(payload)
        assert out["action"] == Action.BLOCKED
        assert out["units_ok"] is False

    def test_blocked_output_has_violations(self):
        payload = bayes_payload()
        payload["inputs"]["p0"] = 0.0
        out = orchestrator.run(payload)
        assert "gate_violations" in out["result"]
        assert len(out["result"]["gate_violations"]) > 0

    def test_negative_hco3_blocked(self):
        payload = abg_payload()
        payload["inputs"]["hco3"] = -10.0
        out = orchestrator.run(payload)
        assert out["action"] == Action.BLOCKED

    def test_blocked_includes_request_id_when_audit_succeeds(self):
        """Respuesta blocked debe incluir request_id si la auditoría se registró."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "blocked_audit.jsonl"
            payload = bayes_payload()
            payload["inputs"]["p0"] = 1.5  # inválido → gate bloquea
            out = orchestrator.run(payload, log_path=log_path)
            assert out["action"] == Action.BLOCKED
            # request_id debe estar presente
            assert "request_id" in out
            assert len(out["request_id"]) == 36  # UUID v4
            # y debe coincidir con el registrado en el log de auditoría
            records = log_path.read_text().strip().split("\n")
            assert len(records) == 1
            log_record = json.loads(records[0])
            assert log_record["request_id"] == out["request_id"]

    def test_blocked_request_id_is_unique_per_call(self):
        """Cada bloqueo debe generar un request_id distinto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "blocked_multi.jsonl"
            payload = bayes_payload()
            payload["inputs"]["p0"] = 1.5
            out1 = orchestrator.run(payload, log_path=log_path)
            out2 = orchestrator.run(payload, log_path=log_path)
            assert out1["request_id"] != out2["request_id"]

    def test_blocked_without_audit_has_no_invented_request_id(self, monkeypatch):
        """Si la auditoría falla durante bloqueo, no se inventa request_id."""
        payload = bayes_payload()
        payload["inputs"]["p0"] = 1.5
        # Forzamos fallo de auditoría de forma portable con monkeypatch,
        # sin depender de rutas del filesystem específicas de Linux.
        from hipocrates.core import audit as audit_module
        monkeypatch.setattr(audit_module, "record", lambda **kw: (_ for _ in ()).throw(OSError("audit forzado a fallar")))
        out = orchestrator.run(payload)
        assert out["action"] == Action.BLOCKED
        # request_id NO debe aparecer si no se pudo auditar
        assert "request_id" not in out


# ── Errores de schema ─────────────────────────────────────────────────────────

class TestSchemaErrors:
    def test_missing_patient_id(self):
        payload = bayes_payload()
        del payload["patient_id"]
        out = orchestrator.run(payload)
        assert out["action"] == Action.ERROR

    def test_unknown_module(self):
        payload = bayes_payload()
        payload["module"] = "sepsis_engine"  # no en este MVP
        out = orchestrator.run(payload)
        assert out["action"] == Action.ERROR

    def test_wrong_version(self):
        payload = bayes_payload()
        payload["version"] = "v2.0"
        out = orchestrator.run(payload)
        assert out["action"] == Action.ERROR

    def test_not_a_dict(self):
        out = orchestrator.run("not a dict")
        assert out["action"] == Action.ERROR


# ── Tres módulos ejecutan sin error ──────────────────────────────────────────

class TestAllModulesRun:
    def test_bayes_runs(self):
        out = orchestrator.run(bayes_payload())
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)

    def test_abg_runs(self):
        out = orchestrator.run(abg_payload())
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)

    def test_dca_runs(self):
        out = orchestrator.run(dca_payload())
        assert out["action"] not in (Action.ERROR, Action.BLOCKED)
