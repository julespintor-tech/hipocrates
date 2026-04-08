"""
validation.py — Validadores de dominio y de payload para Hipócrates.

Complementa Units_Validity_Gate con helpers reutilizables.
"""

from __future__ import annotations
import math
from typing import Any


def is_probability(value: Any) -> bool:
    """True si value ∈ (0, 1) estricto y es finito."""
    try:
        v = float(value)
        return math.isfinite(v) and 0.0 < v < 1.0
    except (TypeError, ValueError):
        return False


def is_non_negative(value: Any) -> bool:
    """True si value ≥ 0 y es finito."""
    try:
        v = float(value)
        return math.isfinite(v) and v >= 0.0
    except (TypeError, ValueError):
        return False


def is_finite(value: Any) -> bool:
    """True si value es finito (no NaN, no inf)."""
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def is_ph_range(value: Any) -> bool:
    """True si value está en rango fisiológico de pH [6.5, 8.0]."""
    try:
        v = float(value)
        return math.isfinite(v) and 6.5 <= v <= 8.0
    except (TypeError, ValueError):
        return False


def is_pco2_range(value: Any) -> bool:
    """True si PaCO2 en rango razonable [5, 120] mmHg."""
    try:
        v = float(value)
        return math.isfinite(v) and 5.0 <= v <= 120.0
    except (TypeError, ValueError):
        return False


def is_hco3_range(value: Any) -> bool:
    """True si HCO3- en rango razonable [1, 60] mEq/L."""
    try:
        v = float(value)
        return math.isfinite(v) and 1.0 <= v <= 60.0
    except (TypeError, ValueError):
        return False
