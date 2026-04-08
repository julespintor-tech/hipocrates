#!/usr/bin/env python3
"""
run_examples.py — Ejecuta los 13 ejemplos del snapshot Hipócrates.

Uso:
    python run_examples.py

Carga los JSON de examples/, los pasa por el orquestador y muestra
la salida completa en consola. Cubre los cinco módulos disponibles:
Bayes SPRT, Ácido-Base H-H/Stewart, DCA, PK/TDM Core v2 y Sepsis Protocol.

ADVERTENCIA: Prototipo de apoyo computable / investigación.
No usar en decisiones clínicas autónomas reales.
"""

import json
import os
import sys
from pathlib import Path

# ── Asegura que src/ esté en el path aunque no se haya instalado el paquete ──
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from hipocrates.core import orchestrator

EXAMPLES_DIR = _ROOT / "examples"

EXAMPLES = [
    ("bayes_example.json",              "Bayes SPRT — Sospecha de sepsis"),
    ("abg_example.json",               "Ácido–Base H–H/Stewart — Acidosis metabólica"),
    ("dca_example.json",               "DCA — Modelo de tromboembolismo"),
    ("pk_iv_bolus_example.json",       "PK_TDM v1 — IV Bolus (1 compartimento)"),
    ("pk_target_dosing_example.json",  "PK_TDM v1 — Target Dosing (LD + MD)"),
    ("pk_phenytoin_mm_example.json",   "PK_TDM v1 — Fenitoína Michaelis–Menten"),
    # ── PK_TDM_Core v2 ────────────────────────────────────────────────────────
    ("pk_cockcroft_gault_example.json",            "PK_TDM v2 — Cockcroft-Gault (CLCr automático)"),
    ("pk_target_dosing_renal_auto_example.json",   "PK_TDM v2 — Target Dosing con ajuste renal automático"),
    ("pk_tdm_bayes_map_single_level_example.json", "PK_TDM v2 — Bayes-MAP con 1 concentración observada"),
    ("pk_tdm_bayes_map_multi_level_example.json",  "PK_TDM v2 — Bayes-MAP con 3 concentraciones observadas"),
    # ── Sepsis_Protocol_Engine ────────────────────────────────────────────────
    ("sepsis_low_risk_example.json",      "Sepsis — Sospecha baja (low_suspicion)"),
    ("sepsis_probable_example.json",      "Sepsis — Sepsis probable"),
    ("septic_shock_probable_example.json","Sepsis — Choque séptico probable"),
]

SEPARATOR = "═" * 70


def _pretty(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def run_example(filename: str, title: str) -> None:
    path = EXAMPLES_DIR / filename
    if not path.exists():
        print(f"[ERROR] Archivo no encontrado: {path}")
        return

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(f"  Archivo: {filename}")
    print(SEPARATOR)

    print("\n── PAYLOAD DE ENTRADA ──────────────────────────────────────────────")
    print(_pretty(payload))

    result = orchestrator.run(payload)

    print("\n── SALIDA DEL ORQUESTADOR ──────────────────────────────────────────")
    # Imprimir campos clave primero, luego el resto
    key_fields = ["action", "p", "U", "NB", "units_ok", "explain", "ci", "request_id"]
    for k in key_fields:
        if k in result:
            val = result[k]
            if isinstance(val, str) and len(val) > 120:
                val = val[:117] + "..."
            print(f"  {k:14}: {val}")

    print("\n── RESULT (detalle) ────────────────────────────────────────────────")
    result_body = result.get("result", {})
    # Omite la curva completa para no inundar la consola
    display = {k: v for k, v in result_body.items() if k not in ("curve_model", "curve_treat_all", "trace")}
    print(_pretty(display))

    if "trace" in result_body:
        trace = result_body["trace"]
        print(f"\n  [trace: {len(trace)} pasos]")
        for step in trace:
            print(f"    paso {step['step']}: {step['test']} LR={step['lr']:.2f} "
                  f"→ p={step['p_after']:.4f}")

    if "curve_model" in result_body:
        curve = result_body["curve_model"]
        print(f"\n  [curva NB modelo: {len(curve)} puntos, "
              f"theta=[{curve[0]['theta']}, …, {curve[-1]['theta']}]]")

    # Resumen específico para sepsis_protocol
    if result_body.get("severity_class"):
        print("\n── SEPSIS PROTOCOL — Resumen ────────────────────────────────────")
        print(f"  Clase de severidad : {result_body.get('severity_class')}")
        print(f"  qSOFA              : {result_body.get('qsofa_score')}/3 "
              f"({'positivo' if result_body.get('qsofa_positive') else 'negativo'})")
        print(f"  SOFA parcial       : {result_body.get('sofa_partial_score')} pts "
              f"({result_body.get('sofa_n_components_evaluated')} componente(s))")
        print(f"  Lactato            : {result_body.get('lactate_mmol_l')} mmol/L "
              f"[{result_body.get('lactate_level')}]")
        print(f"  MAP                : {result_body.get('map_mmhg')} mmHg "
              f"({'BAJA' if result_body.get('map_flag') else 'OK'})")
        print(f"  Vasopresor         : {'SÍ' if result_body.get('vasopressor') else 'NO'}")
        print(f"  Hipoperfusión      : {'SÍ' if result_body.get('hypoperfusion_flag') else 'NO'}")
        print(f"  Revaloración en    : {result_body.get('recheck_time_minutes')} min")
        bundle = result_body.get("bundle_actions", [])
        print(f"\n  Bundle ({len(bundle)} acciones):")
        for i, act in enumerate(bundle, 1):
            print(f"    {i}. {act}")


def main() -> None:
    print("\n" + "═" * 70)
    print("  HIPÓCRATES — Motor de Apoyo Clínico Computable  (SMNC-5+ MVP)")
    print("  ADVERTENCIA: Prototipo de investigación. No uso clínico autónomo.")
    print("═" * 70)

    for filename, title in EXAMPLES:
        try:
            run_example(filename, title)
        except Exception as exc:
            print(f"\n[ERROR al ejecutar {filename}]: {exc}")

    print(f"\n{SEPARATOR}")
    print("  Todos los ejemplos ejecutados.")

    # Verificar que el log de auditoría se generó
    log_path = _ROOT / "outputs" / "audit_log.jsonl"
    if log_path.exists():
        with log_path.open() as f:
            lines = f.readlines()
        print(f"  Auditoría: {len(lines)} registro(s) en outputs/audit_log.jsonl")
    else:
        print("  Auditoría: log no encontrado (revisar permisos de outputs/)")

    print(SEPARATOR + "\n")


if __name__ == "__main__":
    main()
