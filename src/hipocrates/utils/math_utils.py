"""
math_utils.py — Utilidades matemáticas para el sistema Hipócrates.

Funciones de bajo nivel: odds, probabilidad, chequeo numérico.
"""

from __future__ import annotations
import math


def prob_to_odds(p: float) -> float:
    """
    Convierte probabilidad a odds.
    Precondición: p ∈ (0, 1) estricto.
    """
    if not (0 < p < 1):
        raise ValueError(f"Probabilidad fuera de dominio: {p}. Debe estar en (0,1) estricto.")
    return p / (1.0 - p)


def odds_to_prob(odds: float) -> float:
    """
    Convierte odds a probabilidad.
    Precondición: odds > 0.
    """
    if odds <= 0:
        raise ValueError(f"Odds inválidos: {odds}. Deben ser > 0.")
    return odds / (1.0 + odds)


def is_finite_real(x: float) -> bool:
    """Retorna True si x es un número finito y real (no NaN, no inf)."""
    return math.isfinite(x)


def safe_log(x: float) -> float:
    """Logaritmo natural con chequeo de dominio."""
    if x <= 0:
        raise ValueError(f"Argumento inválido para log: {x}. Debe ser > 0.")
    return math.log(x)


def clamp(x: float, lo: float, hi: float) -> float:
    """Limita x al rango [lo, hi]."""
    return max(lo, min(hi, x))
