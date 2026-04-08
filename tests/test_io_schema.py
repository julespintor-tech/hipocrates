"""
test_io_schema.py — Tests del Clinical_IO_Schema.

Cubre:
  - payload válido → ClinicalInput correcto
  - falta de claves → SchemaValidationError
  - module no reconocido → SchemaValidationError
  - patient_id vacío → SchemaValidationError
  - version incorrecta → SchemaValidationError
  - inputs vacío → SchemaValidationError
"""

import pytest
from hipocrates.core.io_schema import (
    SchemaValidationError,
    validate_input,
    REQUIRED_KEYS,
    SCHEMA_VERSION_PREFIX,
)
from hipocrates.utils.types import ClinicalInput


# ── Fixtures ─────────────────────────────────────────────────────────────────

def valid_payload() -> dict:
    return {
        "patient_id": "PAC-TEST-001",
        "module": "bayes_sprt",
        "inputs": {"p0": 0.3, "tests": [], "theta_T": 0.8, "theta_A": 0.1},
        "constraints": {},
        "version": "SMNC-5+_v1.0",
    }


# ── Tests válidos ─────────────────────────────────────────────────────────────

class TestValidInput:
    def test_returns_clinical_input(self):
        result = validate_input(valid_payload())
        assert isinstance(result, ClinicalInput)

    def test_patient_id_preserved(self):
        result = validate_input(valid_payload())
        assert result.patient_id == "PAC-TEST-001"

    def test_module_preserved(self):
        result = validate_input(valid_payload())
        assert result.module == "bayes_sprt"

    def test_version_preserved(self):
        result = validate_input(valid_payload())
        assert result.version == "SMNC-5+_v1.0"

    def test_patient_id_stripped(self):
        p = valid_payload()
        p["patient_id"] = "  PAC-001  "
        result = validate_input(p)
        assert result.patient_id == "PAC-001"

    def test_all_valid_modules(self):
        for module in ("bayes_sprt", "abg_hh_stewart", "dca"):
            p = valid_payload()
            p["module"] = module
            p["inputs"] = {"key": "value"}
            result = validate_input(p)
            assert result.module == module

    def test_constraints_can_be_empty(self):
        p = valid_payload()
        p["constraints"] = {}
        result = validate_input(p)
        assert result.constraints == {}


# ── Tests inválidos ───────────────────────────────────────────────────────────

class TestInvalidInput:
    def test_not_a_dict_raises(self):
        with pytest.raises(SchemaValidationError, match="dict"):
            validate_input("esto no es un dict")

    def test_missing_patient_id(self):
        p = valid_payload()
        del p["patient_id"]
        with pytest.raises(SchemaValidationError, match="patient_id"):
            validate_input(p)

    def test_missing_module(self):
        p = valid_payload()
        del p["module"]
        with pytest.raises(SchemaValidationError, match="module"):
            validate_input(p)

    def test_missing_inputs(self):
        p = valid_payload()
        del p["inputs"]
        with pytest.raises(SchemaValidationError, match="inputs"):
            validate_input(p)

    def test_missing_constraints(self):
        p = valid_payload()
        del p["constraints"]
        with pytest.raises(SchemaValidationError, match="constraints"):
            validate_input(p)

    def test_missing_version(self):
        p = valid_payload()
        del p["version"]
        with pytest.raises(SchemaValidationError, match="version"):
            validate_input(p)

    def test_empty_patient_id_raises(self):
        p = valid_payload()
        p["patient_id"] = "   "
        with pytest.raises(SchemaValidationError, match="patient_id"):
            validate_input(p)

    def test_unknown_module_raises(self):
        p = valid_payload()
        p["module"] = "sepsis_engine"  # no en este MVP
        with pytest.raises(SchemaValidationError, match="Módulo no reconocido"):
            validate_input(p)

    def test_wrong_version_prefix(self):
        p = valid_payload()
        p["version"] = "v1.0"  # no empieza con SMNC-5+
        with pytest.raises(SchemaValidationError, match="version"):
            validate_input(p)

    def test_inputs_not_dict_raises(self):
        p = valid_payload()
        p["inputs"] = [1, 2, 3]
        with pytest.raises(SchemaValidationError, match="inputs"):
            validate_input(p)

    def test_inputs_empty_raises(self):
        p = valid_payload()
        p["inputs"] = {}
        with pytest.raises(SchemaValidationError, match="vacío"):
            validate_input(p)

    def test_constraints_not_dict_raises(self):
        p = valid_payload()
        p["constraints"] = "ninguno"
        with pytest.raises(SchemaValidationError, match="constraints"):
            validate_input(p)
