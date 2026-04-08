"""
ui_helpers.py — Utilidades visuales compartidas para la consola Hipócrates.

No contiene lógica clínica. Solo presentación y formateo de salidas.

Principio de separación de capas:
  - Los módulos clínicos usan valores internos canónicos (snake_case/enums).
  - Esta capa traduce esos valores a lenguaje clínico-natural visible al usuario.
  - El JSON crudo en expanders conserva los valores internos tal cual.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Capa de traducción visible: valores internos → lenguaje clínico-natural
# Los módulos del backend usan estos valores como claves; aquí solo se traduce
# la presentación. Nunca modificar los valores del backend.
# ─────────────────────────────────────────────────────────────────────────────

_ACTIONS_HUMAN: dict[str, str] = {
    "start_treatment":             "Iniciar tratamiento",
    "discard_diagnosis":           "Descartar diagnóstico",
    "obtain_test":                 "Solicitar información adicional",
    "observe":                     "Observar — sin acción inmediata",
    "review_dosing":               "Revisar dosificación",
    "use_model":                   "Usar modelo",
    "do_not_use_model":            "No usar modelo",
    "restrict_to_threshold_range": "Útil solo en un subrango de decisión",
    "blocked":                     "Ejecución rechazada por validación de dominio",
    "error":                       "Error del sistema",
}

_ABG_PRIMARY_HUMAN: dict[str, str] = {
    "acidosis_metabolica":    "Acidosis metabólica",
    "acidosis_respiratoria":  "Acidosis respiratoria",
    "alcalosis_metabolica":   "Alcalosis metabólica",
    "alcalosis_respiratoria": "Alcalosis respiratoria",
    "ph_normal":              "pH dentro de rango fisiológico",
}

_ABG_COMPENSATION_HUMAN: dict[str, str] = {
    "no_evaluada":        "No evaluada en este caso",
    "indeterminado":      "Indeterminado",
    "compensacion_respiratoria_adecuada":
        "Compensación respiratoria adecuada",
    "hiperventilacion_adicional_alcalosis_respiratoria_concomitante":
        "Hiperventilación adicional — alcalosis respiratoria concomitante",
    "hipoventilacion_acidosis_respiratoria_concomitante":
        "Hipoventilación — acidosis respiratoria concomitante",
    "compensacion_renal_aguda":          "Compensación renal aguda",
    "compensacion_renal_cronica":        "Compensación renal crónica",
    "compensacion_renal_no_adecuada":    "Compensación renal no adecuada",
}

_ABG_DELTA_DELTA_HUMAN: dict[str, str] = {
    "acidosis_metabolica_anion_gap_puro":
        "Acidosis metabólica pura con brecha aniónica elevada",
    "AG_elevado_con_acidosis_metabolica_hipercloremia_concomitante":
        "AG elevado con acidosis metabólica hiperclorémica concomitante",
    "alcalosis_metabolica_concomitante_o_AG_elevado_previo":
        "Alcalosis metabólica concomitante o brecha aniónica elevada previa",
}


def humanize_action(action: str) -> str:
    """Traduce acción canónica interna a etiqueta visible en español clínico."""
    return _ACTIONS_HUMAN.get(action, action.replace("_", " ").capitalize())


def humanize_abg_primary(value: str) -> str:
    """Traduce primary_disorder a etiqueta clínica visible."""
    return _ABG_PRIMARY_HUMAN.get(value, value.replace("_", " ").capitalize())


def humanize_abg_compensation(value: str) -> str:
    """Traduce compensation a etiqueta clínica visible."""
    return _ABG_COMPENSATION_HUMAN.get(value, value.replace("_", " ").capitalize())


def humanize_abg_delta_delta(value: str) -> str:
    """Traduce delta_delta_interpretation a etiqueta clínica visible."""
    return _ABG_DELTA_DELTA_HUMAN.get(value, value.replace("_", " ").capitalize())


def humanize_formal_label(primary: str, compensation: str) -> str:
    """Construye la etiqueta diagnóstica formal legible combinando primary y compensation."""
    p_human = humanize_abg_primary(primary)
    if not compensation or compensation in ("no_evaluada", "indeterminado"):
        return p_human
    c_human = humanize_abg_compensation(compensation)
    # La compensación va en minúsculas cuando sigue a "con" (en mitad de frase)
    c_inline = c_human[0].lower() + c_human[1:] if c_human else c_human
    return f"{p_human} con {c_inline}"


# ─────────────────────────────────────────────────────────────────────────────
# Capa de traducción: Sepsis_Protocol_Engine
# Valores internos del módulo → etiquetas clínicas visibles en español
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_CLASS_HUMAN: dict[str, str] = {
    "low_suspicion":          "Sospecha baja de sepsis",
    "sepsis_probable":        "Sepsis probable",
    "septic_shock_probable":  "Choque séptico probable",
}

_LACTATE_LEVEL_HUMAN: dict[str, str] = {
    "normal":             "Normal",
    "borderline":         "Zona limítrofe (≥ 1.5 mmol/L)",
    "elevated":           "Elevado (≥ 2.0 mmol/L)",
    "markedly_elevated":  "Marcadamente elevado (≥ 4.0 mmol/L)",
}


def humanize_severity_class(value: str) -> str:
    """Traduce severity_class interna a etiqueta clínica visible en español."""
    return _SEVERITY_CLASS_HUMAN.get(value, value.replace("_", " ").capitalize())


def humanize_lactate_level(value: str) -> str:
    """Traduce lactate_level interno a etiqueta clínica visible en español."""
    return _LACTATE_LEVEL_HUMAN.get(value, value.replace("_", " ").capitalize())


# ─────────────────────────────────────────────────────────────────────────────
# Colores y etiquetas de acciones canónicas
# ─────────────────────────────────────────────────────────────────────────────

_ACTION_STYLE: dict[str, tuple[str, str]] = {
    # (color_fondo_hex, etiqueta_es)
    # Etiquetas sincronizadas con _ACTIONS_HUMAN para coherencia en toda la UI.
    # Las acciones son decisiones computacionales, no prescripciones autónomas.
    "start_treatment":             ("#2d7a2d", "✅ Iniciar tratamiento"),
    "discard_diagnosis":           ("#1a5fa8", "🔵 Descartar diagnóstico"),
    "obtain_test":                 ("#a86f1a", "🔶 Solicitar información adicional"),
    "observe":                     ("#555555", "👁 Observar — sin acción inmediata"),
    "review_dosing":               ("#7a5c00", "⚠️ Revisar dosificación"),
    "use_model":                   ("#2d7a2d", "✅ Usar modelo"),
    "do_not_use_model":            ("#8b1a1a", "🚫 No usar modelo"),
    "restrict_to_threshold_range": ("#a86f1a", "🔶 Útil solo en un subrango de decisión"),
    "error":                       ("#8b1a1a", "❌ Error del sistema"),
    "blocked":                     ("#8b1a1a", "🔒 Ejecución rechazada por validación de dominio"),
}


def render_action_badge(action: str) -> None:
    """Muestra la acción como badge de color."""
    color, label = _ACTION_STYLE.get(action, ("#444444", f"⬜ {action}"))
    st.markdown(
        f'<span style="background:{color};color:#fff;padding:6px 14px;'
        f'border-radius:6px;font-weight:700;font-size:1.05em;">'
        f'{label}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")  # espacio


def render_explain(explain: str) -> None:
    """Muestra el texto explain en un callout."""
    st.info(f"**Razonamiento del sistema:** {explain}")


def render_blocked_error(output: dict[str, Any]) -> None:
    """Muestra mensajes de error o bloqueo del gate, incluyendo trazabilidad si existe."""
    action = output.get("action", "error")
    explain = output.get("explain", "Sin detalle.")
    result = output.get("result", {})

    if action == "blocked":
        st.error("**🔒 Ejecución rechazada — violación de dominio (Units Gate)**")
        st.caption(
            "El sistema validó los inputs antes de ejecutar el módulo clínico. "
            "La solicitud fue rechazada porque uno o más valores caen fuera del "
            "dominio matemático o clínico aceptable. No se ejecutó ningún cálculo."
        )
        violations = result.get("gate_violations", [])
        if violations:
            for v in violations:
                st.markdown(f"- {v}")
    elif action == "error":
        st.error(f"**❌ Error del sistema:** {explain}")
    else:
        st.warning(f"**Acción inesperada ({action}):** {explain}")

    # Trazabilidad: request_id y units_ok se muestran aunque la solicitud fuera bloqueada,
    # porque el sistema registra auditoría incluso de solicitudes rechazadas.
    request_id = output.get("request_id")
    units_ok = output.get("units_ok")
    if request_id is not None or units_ok is not None:
        cols = st.columns(2)
        with cols[0]:
            st.text_input(
                "ID de solicitud (request_id)",
                value=request_id if request_id else "—",
                disabled=True,
                key=f"blocked_rid_{id(output)}",
            )
        with cols[1]:
            st.text_input(
                "Validación de dominio (units_ok)",
                value="✅ Válido" if units_ok else "❌ Inválido",
                disabled=True,
                key=f"blocked_uok_{id(output)}",
            )


def render_raw_json(output: dict[str, Any], label: str = "Output completo (JSON)") -> None:
    """Muestra el output completo en un expander."""
    with st.expander(f"🔍 {label}", expanded=False):
        st.json(output)


def render_audit_fields(output: dict[str, Any]) -> None:
    """Muestra los campos de auditoría de un output."""
    cols = st.columns(2)
    with cols[0]:
        if "request_id" in output:
            st.text_input(
                "ID de solicitud (request_id)",
                value=output["request_id"],
                disabled=True,
                help="Identificador único UUID de esta ejecución. Vincula el output visible "
                     "con el registro de auditoría JSONL correspondiente.",
            )
    with cols[1]:
        units_ok = output.get("units_ok", False)
        st.text_input(
            "Validación de dominio (units_ok)",
            value="✅ Válido" if units_ok else "❌ Inválido",
            disabled=True,
            help="Indica si todos los inputs pasaron la validación de dominio del Units Gate "
                 "antes de la ejecución del módulo clínico.",
        )


def render_metric_row(items: list[tuple[str, Any]]) -> None:
    """Muestra una fila de métricas con label / valor."""
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        with col:
            if value is None:
                st.metric(label, "—")
            elif isinstance(value, float):
                st.metric(label, f"{value:.4f}")
            else:
                st.metric(label, str(value))


def section_header(title: str, subtitle: str = "") -> None:
    """Cabecera de sección con línea horizontal."""
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.markdown("---")


def warning_prototype() -> None:
    """Banner de advertencia de prototipo."""
    st.warning(
        "⚠️ **PROTOTIPO DE INVESTIGACIÓN** — Los outputs son estimaciones computacionales, "
        "no decisiones clínicas autónomas. Requieren interpretación por personal clínico "
        "competente. El sistema desconoce el contexto clínico completo del paciente. "
        "No reemplaza la evaluación médica directa.",
        icon=None,
    )
