"""
streamlit_app.py — Consola visual local de Hipócrates (SMNC-5+ MVP)

Interfaz Streamlit que conecta al núcleo real del sistema.
NO reimplementa lógica clínica. Solo recoge inputs, llama al orquestador
y presenta resultados.

Uso:
    streamlit run app/streamlit_app.py

ADVERTENCIA: Prototipo de investigación. No uso clínico autónomo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# ── Path: asegura que el paquete sea importable aunque no esté instalado ──────
_APP_DIR = Path(__file__).resolve().parent
_ROOT = _APP_DIR.parent
sys.path.insert(0, str(_ROOT / "src"))

from hipocrates.core import orchestrator          # noqa: E402
from hipocrates.utils.types import Action         # noqa: E402

# ui_helpers está en el mismo directorio que este script
sys.path.insert(0, str(_APP_DIR))
from ui_helpers import (                          # noqa: E402
    render_action_badge,
    render_explain,
    render_blocked_error,
    render_raw_json,
    render_audit_fields,
    render_metric_row,
    section_header,
    warning_prototype,
    humanize_action,
    humanize_abg_primary,
    humanize_abg_compensation,
    humanize_abg_delta_delta,
    humanize_formal_label,
    humanize_severity_class,
    humanize_lactate_level,
)

# ─────────────────────────────────────────────────────────────────────────────
# Configuración global
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "SMNC-5+_v1.0"
LOG_PATH = _ROOT / "outputs" / "audit_log.jsonl"

st.set_page_config(
    page_title="Hipócrates — Consola SMNC-5+",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar / navegación
# ─────────────────────────────────────────────────────────────────────────────

PAGES = {
    "🏠  Inicio": "home",
    "🎲  Bayes SPRT": "bayes",
    "🫁  Ácido–Base": "abg",
    "📊  DCA": "dca",
    "💊  PK / TDM": "pk_tdm",
    "🔴  Sepsis": "sepsis",
    "📋  Auditoría": "auditoria",
}

with st.sidebar:
    st.markdown("## ⚕️ Hipócrates")
    st.caption("Motor de Apoyo Clínico Computable — SMNC-5+")
    st.markdown("---")
    page_label = st.radio("Módulo", list(PAGES.keys()), label_visibility="collapsed")
    st.markdown("---")
    st.caption("v1.0 · Prototipo local · No uso clínico autónomo")

page = PAGES[page_label]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _run(payload: dict[str, Any]) -> dict[str, Any]:
    """Llama al orquestador y devuelve el resultado."""
    return orchestrator.run(payload, log_path=LOG_PATH)


def _is_ok(output: dict[str, Any]) -> bool:
    return output.get("action") not in (Action.ERROR, Action.BLOCKED)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: HOME
# ─────────────────────────────────────────────────────────────────────────────

def page_home() -> None:
    section_header("⚕️ Hipócrates — Motor de Apoyo Clínico Computable",
                   "Sistema Médico Núcleo Computable SMNC-5+")
    warning_prototype()
    st.markdown("")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ¿Qué es Hipócrates?")
        st.markdown(
            "Hipócrates es un **motor determinista de apoyo clínico computable** basado en el "
            "Sistema Médico Núcleo Computable **SMNC-5+**. Implementa algoritmos formales de "
            "razonamiento bayesiano secuencial, interpretación gasométrica ácido-base, análisis "
            "de utilidad clínica por curva de decisión y cálculo farmacocinético monocompartimental, "
            "con salida estructurada homogénea, auditoría criptográfica integrada y validación de "
            "dominio estricta antes de cada cálculo.\n\n"
            "**No es** un sistema de IA generativa ni un chatbot médico. Cada cálculo es "
            "reproducible, auditable y formalmente verificable. Los outputs son "
            "**estimaciones computacionales**: no reemplazan la evaluación clínica directa "
            "ni incorporan el contexto clínico completo del paciente."
        )

        st.markdown("### Módulos disponibles")
        modules = {
            "🎲 Bayes SPRT": (
                "Actualización bayesiana secuencial con parada temprana real (SPRT de Wald). "
                "Estima la probabilidad posterior de un diagnóstico a partir de probabilidad "
                "pretest y razones de verosimilitud (LR) de tests secuenciales. "
                "Se detiene en cuanto se cruza un umbral de tratamiento (θ_T) o descarte (θ_A)."
            ),
            "🫁 Ácido–Base H–H / Stewart": (
                "Interpretación gasométrica formal con Henderson-Hasselbalch y aproximación "
                "Stewart-Fencl. Calcula trastorno primario, compensación esperada, brecha "
                "aniónica (AG y AG corregido por albúmina), delta-delta, fórmula de Winter, "
                "SIDa y Atot."
            ),
            "📊 DCA — Decision Curve Analysis": (
                "Análisis de utilidad clínica por curva de decisión. Calcula beneficio neto "
                "(NB) del modelo diagnóstico frente a las estrategias de referencia "
                "'tratar-todos' y 'no-tratar' en un rango de umbrales de probabilidad θ."
            ),
            "💊 PK / TDM Core v2": (
                "Farmacocinética monocompartimental (1C) con 10 modos: IV bolus, infusión IV, "
                "dosis múltiples, oral Bateman, target dosing, Michaelis-Menten fenitoína, "
                "ajuste renal proporcional (v1) + Cockcroft-Gault, target dosing con ajuste renal "
                "automático y TDM Bayes-MAP básico (v2, sin MCMC). "
                "Todos los outputs son orientativos y requieren confirmación con niveles séricos."
            ),
            "🔴 Sepsis — Protocolo Computacional de Apoyo": (
                "Estratificación de sospecha de sepsis basada en criterios Sepsis-3 adaptados "
                "para computabilidad parcial. Calcula qSOFA, SOFA parcial (con los componentes "
                "disponibles), evalúa lactato, MAP y soporte vasopresor. Clasifica severidad en "
                "Sospecha baja / Sepsis probable / Choque séptico probable, genera bundle de "
                "acciones de alto nivel y fija tiempo de revaloración. "
                "No prescribe antibióticos específicos. No reemplaza valoración clínica directa."
            ),
        }
        for name, desc in modules.items():
            st.markdown(f"**{name}**  \n{desc}")
            st.markdown("")

    with col2:
        st.markdown("### Arquitectura del sistema")
        st.code(
            "hipocrates/\n"
            "  src/hipocrates/\n"
            "    core/\n"
            "      io_schema.py         # Valida estructura del payload de entrada\n"
            "      units_gate.py        # Rechaza inputs fuera de dominio antes de calcular\n"
            "      audit.py             # Registra SHA-256 dual + UUID en JSONL\n"
            "      orchestrator.py      # Pipeline: schema → gate → módulo → auditoría\n"
            "    modules/\n"
            "      bayes_sprt.py        # SPRT de Wald\n"
            "      abg_hh_stewart.py    # H-H + Stewart-Fencl\n"
            "      dca.py               # Decision Curve Analysis\n"
            "      pk_tdm.py            # PK_TDM_Core v2.0 (10 modos)\n"
            "      sepsis_protocol.py   # Sepsis_Protocol_Engine v1\n"
            "    utils/\n"
            "      types.py             # ClinicalInput / ClinicalOutput / Action\n"
            "  app/\n"
            "    streamlit_app.py       # Esta consola visual\n"
            "  tests/                   # 338 tests pytest",
            language="text",
        )

        st.markdown("### Estructura de respuesta del sistema")
        st.caption(
            "Todos los módulos devuelven exactamente este formato. "
            "Los campos de alto nivel (`action`, `p`, `NB`, `units_ok`, `request_id`) "
            "son homogéneos entre módulos; `result` contiene los datos específicos del cálculo."
        )
        st.json({
            "result":     "{ datos específicos del módulo }",
            "action":     "start_treatment | discard_diagnosis | obtain_test | observe | review_dosing | use_model | ...",
            "p":          "probabilidad posterior (Bayes) — null en otros módulos",
            "U":          "utilidad clínica esperada — reservado, null en v1.0",
            "NB":         "beneficio neto (DCA) — null en otros módulos",
            "units_ok":   "true si los inputs superaron la validación de dominio",
            "explain":    "razonamiento textual del sistema para este output",
            "ci":         "intervalo de confianza — null en v1.0 (reservado)",
            "request_id": "UUID único de esta ejecución — enlaza output con registro de auditoría",
        })

        with st.expander("¿Cómo leer una acción canónica?"):
            st.markdown(
                "El campo `action` es la **decisión computacional de alto nivel** del sistema. "
                "No es una orden clínica autónoma — es una clasificación formal del resultado "
                "que sirve de orientación al clínico:\n\n"
                f"- **{humanize_action('start_treatment')}** (`start_treatment`) — "
                "la probabilidad posterior superó el umbral de tratamiento θ_T\n"
                f"- **{humanize_action('discard_diagnosis')}** (`discard_diagnosis`) — "
                "la probabilidad posterior cayó por debajo del umbral de descarte θ_A\n"
                f"- **{humanize_action('obtain_test')}** (`obtain_test`) — "
                "el SPRT no alcanzó ningún umbral; la evidencia acumulada es insuficiente para decidir\n"
                f"- **{humanize_action('observe')}** (`observe`) — "
                "resultado calculado, sin indicación de acción inmediata\n"
                f"- **{humanize_action('review_dosing')}** (`review_dosing`) — "
                "cálculo PK/TDM orientativo; requiere revisión clínica y confirmación sérica\n"
                f"- **{humanize_action('use_model')}** / **{humanize_action('do_not_use_model')}** "
                "(`use_model` / `do_not_use_model`) — el modelo DCA genera (o no) beneficio neto en θ\n"
                f"- **{humanize_action('restrict_to_threshold_range')}** (`restrict_to_threshold_range`) — "
                "el modelo DCA es útil solo en un subconjunto del rango evaluado\n"
                f"- **{humanize_action('blocked')}** (`blocked`) — "
                "los inputs no superaron validación de dominio; no se ejecutó ningún cálculo\n"
            )

    st.markdown("---")
    st.caption(
        "Uso aceptable: investigación, educación, simulación, prototipado de sistemas de apoyo a la decisión. "
        "Uso inaceptable: decisiones clínicas autónomas, prescripción, diagnóstico definitivo sin supervisión médica."
    )


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: BAYES SPRT
# ─────────────────────────────────────────────────────────────────────────────

def page_bayes() -> None:
    section_header("🎲 Bayes SPRT", "Actualización bayesiana secuencial — SPRT de Wald")
    warning_prototype()

    with st.expander("¿Cómo interpretar este módulo?", expanded=False):
        st.markdown(
            "**Bayes SPRT** combina razonamiento bayesiano con el procedimiento secuencial de "
            "razón de probabilidad de Wald (SPRT) para actualizar la probabilidad de un diagnóstico "
            "a medida que se incorporan resultados de tests.\n\n"
            "**Parámetros clave:**\n"
            "- **p₀ (probabilidad pretest):** estimación clínica de la probabilidad del diagnóstico "
            "*antes* de aplicar ningún test. Corresponde a la prevalencia ajustada al contexto del paciente.\n"
            "- **θ_T (umbral de tratamiento):** si la probabilidad posterior p ≥ θ_T, el sistema "
            "emite `start_treatment`. Por encima de este umbral, la evidencia se considera suficiente para tratar.\n"
            "- **θ_A (umbral de descarte):** si p ≤ θ_A, el sistema emite `discard_diagnosis`. "
            "Por debajo de este umbral, la evidencia es suficiente para descartar.\n"
            "- **LR (razón de verosimilitud):** cociente entre la probabilidad del resultado del test "
            "dado que el diagnóstico es verdadero y dado que es falso. LR > 1 aumenta p; LR < 1 la disminuye.\n"
            "- **Resultado pos/neg:** indica si el test resultó positivo (se usa LR tal cual) o "
            "negativo (se usa 1/LR, el inverso de la razón de verosimilitud).\n\n"
            "**Parada temprana:** el SPRT se detiene en cuanto p cruza θ_T o θ_A. "
            "Los tests restantes no se procesan — esto no es un error, sino la decisión formal "
            "del procedimiento: con la información acumulada ya es posible decidir sin tests adicionales.\n\n"
            "**`obtain_test`:** si ningún umbral se cruza al agotar todos los tests, el sistema "
            "indica que la evidencia disponible es insuficiente para decidir y se requiere información adicional."
        )

    # ── Inicializar lista de tests en session_state ───────────────────────────
    if "bayes_tests" not in st.session_state:
        st.session_state.bayes_tests = [{"name": "", "lr": 1.0, "result": "pos"}]

    col_form, col_result = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("#### Parámetros")
        patient_id = st.text_input("patient_id", value="PAC-001", key="bayes_pid")
        p0 = st.slider(
            "p₀ — Probabilidad pretest del diagnóstico",
            0.01, 0.99, 0.25, 0.01,
            help="Estimación de la probabilidad del diagnóstico antes de aplicar los tests. "
                 "Equivale a la prevalencia ajustada al contexto clínico del paciente.",
        )
        theta_T = st.slider(
            "θ_T — Umbral de tratamiento (p ≥ θ_T → tratar)",
            0.50, 0.99, 0.80, 0.01,
            help="Si la probabilidad posterior supera este umbral, el sistema emite 'start_treatment'.",
        )
        theta_A = st.slider(
            "θ_A — Umbral de descarte (p ≤ θ_A → descartar)",
            0.01, 0.30, 0.05, 0.01,
            help="Si la probabilidad posterior cae por debajo de este umbral, el sistema emite 'discard_diagnosis'.",
        )

        st.markdown("#### Tests secuenciales")
        st.caption(
            "Cada test se define por su **LR** (razón de verosimilitud positiva) y si su resultado fue "
            "**pos** (positivo, se aplica LR) o **neg** (negativo, se aplica 1/LR)."
        )
        tests_to_delete = []
        for i, test in enumerate(st.session_state.bayes_tests):
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                with c1:
                    test["name"] = st.text_input(
                        "Nombre del test", value=test["name"],
                        key=f"b_name_{i}", placeholder=f"Test {i+1}"
                    )
                with c2:
                    test["lr"] = st.number_input(
                        "LR (+)", min_value=0.01, max_value=200.0,
                        value=float(test["lr"]), step=0.1, key=f"b_lr_{i}",
                        help="Razón de verosimilitud positiva del test. Se usa LR si positivo, 1/LR si negativo.",
                    )
                with c3:
                    _res_opts = {"Positivo": "pos", "Negativo": "neg"}
                    _res_display = [k for k, v in _res_opts.items() if v == test["result"]]
                    _res_sel = st.selectbox(
                        "Resultado", list(_res_opts.keys()),
                        index=0 if test["result"] == "pos" else 1,
                        key=f"b_res_{i}",
                        help="Positivo: aplica LR tal cual. Negativo: aplica 1/LR (inverso).",
                    )
                    test["result"] = _res_opts[_res_sel]
                with c4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("✕", key=f"b_del_{i}", help="Eliminar test"):
                        tests_to_delete.append(i)

        for i in sorted(tests_to_delete, reverse=True):
            st.session_state.bayes_tests.pop(i)

        if st.button("➕ Añadir test"):
            st.session_state.bayes_tests.append({"name": "", "lr": 1.0, "result": "pos"})
            st.rerun()

        st.markdown("")
        run_btn = st.button("▶️ Ejecutar Bayes SPRT", type="primary", use_container_width=True)

    with col_result:
        st.markdown("#### Resultado")
        if run_btn:
            tests_payload = [
                {
                    "name": t["name"] or f"test_{i+1}",
                    "lr": t["lr"] if t["result"] == "pos" else 1.0 / t["lr"],
                    "result": t["result"],
                }
                for i, t in enumerate(st.session_state.bayes_tests)
            ]
            payload = {
                "patient_id": patient_id.strip() or "PAC-001",
                "module": "bayes_sprt",
                "inputs": {
                    "p0": p0,
                    "tests": tests_payload,
                    "theta_T": theta_T,
                    "theta_A": theta_A,
                },
                "constraints": {},
                "version": SCHEMA_VERSION,
            }

            with st.spinner("Calculando..."):
                output = _run(payload)

            if not _is_ok(output):
                render_blocked_error(output)
            else:
                render_action_badge(output["action"])
                render_audit_fields(output)

                p_post = output.get("p")
                ci = output.get("ci")
                result = output.get("result", {})

                render_metric_row([
                    ("p₀ — probabilidad pretest", p0),
                    ("p posterior", p_post),
                    ("Tests procesados", result.get("n_tests_applied")),
                    ("Tests no procesados (parada temprana)", len(result.get("tests_skipped", []))),
                ])

                if ci:
                    st.caption(f"IC 95% nominal: {ci.get('95%_nominal', '—')}")

                # Parada temprana
                stopped = result.get("sprt_stopped_at_step")
                n_provided = result.get("n_tests_provided", 0)
                if stopped and stopped < n_provided:
                    st.success(
                        f"⏹ Parada temprana SPRT en paso {stopped} de {n_provided} posibles. "
                        f"Los {n_provided - stopped} tests restantes no fueron procesados: "
                        "la evidencia acumulada fue suficiente para cruzar un umbral de decisión."
                    )

                # Traza
                trace = result.get("trace", [])
                if trace:
                    st.markdown("**Traza de actualización secuencial**")
                    st.caption(
                        "Cada fila muestra la probabilidad posterior acumulada tras aplicar el test. "
                        "LR < 1 indica test negativo (se aplicó el inverso de la LR positiva)."
                    )
                    rows = []
                    for step in trace:
                        rows.append({
                            "Paso": step["step"],
                            "Test": step["test"],
                            "LR aplicado": f"{step['lr']:.3f}",
                            "p posterior al test": f"{step['p_after']:.4f}",
                        })
                    st.dataframe(rows, use_container_width=True, hide_index=True)

                render_explain(output.get("explain", ""))
                render_raw_json(output)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: ÁCIDO–BASE
# ─────────────────────────────────────────────────────────────────────────────

def page_abg() -> None:
    section_header("🫁 Ácido–Base H–H / Stewart",
                   "Interpretación gasométrica formal — Henderson-Hasselbalch + aproximación Stewart-Fencl")
    warning_prototype()

    with st.expander("¿Cómo interpretar este módulo?", expanded=False):
        st.markdown(
            "Este módulo integra dos marcos formales de interpretación gasométrica:\n\n"
            "**Henderson-Hasselbalch (H-H):** interpreta el equilibrio ácido-base mediante pH, "
            "PaCO₂ y HCO₃⁻. Identifica el trastorno primario (acidosis/alcalosis, respiratoria/metabólica), "
            "verifica la compensación esperada y calcula el pH teórico para contrastar con el medido.\n\n"
            "**Aproximación Stewart-Fencl:** marcos fisicoquímico que analiza los determinantes "
            "independientes del pH (SIDa y Atot). Esta implementación es una *aproximación*, no la versión "
            "completa del modelo Stewart. Requiere electrólitos adicionales y niveles de albúmina/fosfato.\n\n"
            "**Brecha aniónica (AG):** AG = Na⁺ − (Cl⁻ + HCO₃⁻). Detecta aniones no medidos. "
            "**AG corregido por albúmina:** compensa el efecto de la hipoalbuminemia sobre el AG. "
            "Sin corrección, la hipoalbuminemia enmascara una brecha aniónica elevada.\n\n"
            "**Delta-delta (Δ/Δ):** evalúa si existe un trastorno metabólico mixto subyacente en "
            "presencia de AG elevado. Δ/Δ = (AG − 12) / (24 − HCO₃⁻).\n\n"
            "**Winter:** fórmula de compensación respiratoria esperada en acidosis metabólica. "
            "PaCO₂ esperada = 1.5 × HCO₃⁻ + 8 ± 2. Si la PaCO₂ real cae fuera de ese rango, "
            "sugiere un trastorno respiratorio superpuesto.\n\n"
            "**SIDa (Diferencia iónica fuerte aparente):** SIDa = Na⁺ + K⁺ + Ca²⁺ + Mg²⁺ − Cl⁻ − Lactato. "
            "**Atot (buffer no volátil total):** Atot = 2.43 × albúmina + fosfato/5.5.\n\n"
            "**Consistencia:** el sistema recalcula el pH por H-H a partir de PaCO₂ y HCO₃⁻ y "
            "lo compara con el pH medido. Una discrepancia > 0.05 sugiere error de laboratorio o "
            "valores introducidos inconsistentes entre sí."
        )

    col_form, col_result = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("#### Parámetros gasométricos")
        patient_id = st.text_input("patient_id", value="PAC-002", key="abg_pid")
        c1, c2, c3 = st.columns(3)
        with c1:
            ph = st.number_input("pH", 6.5, 8.0, 7.40, 0.01, format="%.2f")
        with c2:
            paco2 = st.number_input("PaCO₂ (mmHg)", 5.0, 120.0, 40.0, 0.5)
        with c3:
            hco3 = st.number_input("HCO₃⁻ (mEq/L)", 1.0, 60.0, 24.0, 0.5)

        c4, c5, c6 = st.columns(3)
        with c4:
            na = st.number_input("Na⁺ (mEq/L)", 100.0, 180.0, 140.0, 1.0)
        with c5:
            k = st.number_input("K⁺ (mEq/L)", 1.0, 9.0, 4.0, 0.1)
        with c6:
            cl = st.number_input("Cl⁻ (mEq/L)", 60.0, 140.0, 104.0, 1.0)

        st.markdown("#### Electrólitos adicionales — AG corregido y estimación Stewart-Fencl")
        with st.expander("Mostrar campos opcionales"):
            oc1, oc2 = st.columns(2)
            with oc1:
                albumin = st.number_input("Albúmina (g/dL)", 0.0, 8.0, 4.0, 0.1)
                phosphate = st.number_input("Fosfato (mg/dL)", 0.0, 10.0, 3.5, 0.1)
            with oc2:
                ca = st.number_input("Ca²⁺ (mEq/L)", 0.0, 15.0, 5.0, 0.1)
                mg = st.number_input("Mg²⁺ (mEq/L)", 0.0, 6.0, 1.8, 0.1)
                lactate = st.number_input("Lactato (mEq/L)", 0.0, 20.0, 1.0, 0.1)

        st.markdown("")
        run_btn = st.button("▶️ Interpretar gasometría", type="primary", use_container_width=True)

    with col_result:
        st.markdown("#### Resultado")
        if run_btn:
            payload = {
                "patient_id": patient_id.strip() or "PAC-002",
                "module": "abg_hh_stewart",
                "inputs": {
                    "ph": ph, "paco2": paco2, "hco3": hco3,
                    "na": na, "k": k, "cl": cl,
                    "albumin_g_dl": albumin,
                    "phosphate_mg_dl": phosphate,
                    "ca_meq_l": ca,
                    "mg_meq_l": mg,
                    "lactate_meq_l": lactate,
                },
                "constraints": {},
                "version": SCHEMA_VERSION,
            }
            with st.spinner("Interpretando..."):
                output = _run(payload)

            if not _is_ok(output):
                render_blocked_error(output)
            else:
                render_action_badge(output["action"])
                render_audit_fields(output)

                result = output.get("result", {})

                # Diagnóstico principal — valores internos traducidos a lenguaje clínico
                _raw_primary = result.get("primary_disorder", "")
                _raw_comp    = result.get("compensation", "")
                st.markdown(f"**Trastorno primario:** {humanize_abg_primary(_raw_primary) if _raw_primary else '—'}")
                st.markdown(f"**Compensación esperada:** {humanize_abg_compensation(_raw_comp) if _raw_comp else '—'}")
                st.markdown(f"**Diagnóstico gasométrico formal:** {humanize_formal_label(_raw_primary, _raw_comp) if _raw_primary else '—'}")

                consist = result.get("consistency_ok")
                if consist is True:
                    st.success(
                        f"pH calculado (H-H): {result.get('ph_calculated_hh', '—')} "
                        f"(Δ = {result.get('ph_discrepancy', '—')} — consistente con pH medido)"
                    )
                else:
                    st.warning(
                        f"pH calculado (H-H): {result.get('ph_calculated_hh', '—')} "
                        f"(Δ = {result.get('ph_discrepancy', '—')} — ⚠️ discrepancia con pH medido: "
                        "verificar valores introducidos o posible error de laboratorio)"
                    )

                st.markdown("---")

                # Anion gap
                render_metric_row([
                    ("AG — brecha aniónica", result.get("anion_gap")),
                    ("AG corregido por albúmina", result.get("anion_gap_corrected")),
                    ("AG elevado", "Sí" if result.get("ag_elevated") else "No"),
                    ("Delta-delta (Δ/Δ)", result.get("delta_delta")),
                ])
                dd_interp = result.get("delta_delta_interpretation", "")
                if dd_interp:
                    st.caption(f"Interpretación Δ/Δ: {humanize_abg_delta_delta(dd_interp)}")

                # Winter
                winter = result.get("winter_expected_paco2", {})
                if winter:
                    w_lo = winter.get("lo", "—")
                    w_hi = winter.get("hi", "—")
                    in_range = w_lo <= paco2 <= w_hi if isinstance(w_lo, float) else None
                    st.info(
                        f"**PaCO₂ esperado Winter:** [{w_lo}, {w_hi}] mmHg — "
                        f"PaCO₂ actual {paco2} mmHg → "
                        f"{'✅ dentro del rango' if in_range else ('⚠️ fuera del rango' if in_range is False else '—')}"
                    )

                # Stewart
                st.markdown("**Estimación Stewart-Fencl (aproximación):**")
                st.caption(
                    "SIDa = diferencia iónica fuerte aparente. "
                    "Atot = buffer no volátil total (albúmina + fosfato). "
                    "Estos valores son una aproximación al marco fisicoquímico completo de Stewart."
                )
                render_metric_row([
                    ("SIDa — Dif. iónica fuerte aparente (mEq/L)", result.get("SIDa")),
                    ("Atot — Buffer no volátil total (mEq/L)", result.get("Atot")),
                ])
                if result.get("stewart_note"):
                    st.caption(result["stewart_note"])

                render_explain(output.get("explain", ""))

                with st.expander("🔍 Detalle técnico completo"):
                    st.caption(
                        "Los valores internos como 'acidosis_metabolica' o 'compensacion_renal_aguda' "
                        "son las claves canónicas del sistema. En la sección principal de resultados "
                        "aparecen traducidos a lenguaje clínico."
                    )
                    display = {k: v for k, v in result.items()
                               if k not in ("formal_label", "stewart_note")}
                    st.json(display)

                render_raw_json(output)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: DCA
# ─────────────────────────────────────────────────────────────────────────────

def page_dca() -> None:
    section_header("📊 DCA — Decision Curve Analysis",
                   "Análisis de utilidad clínica por curva de beneficio neto")
    warning_prototype()

    with st.expander("¿Cómo interpretar este módulo?", expanded=False):
        st.markdown(
            "**Decision Curve Analysis (DCA)** evalúa la utilidad clínica de un modelo diagnóstico "
            "calculando su **beneficio neto (NB)** en función del umbral de probabilidad θ para "
            "la decisión clínica. El análisis compara el modelo frente a dos estrategias de referencia:\n\n"
            "- **Tratar-todos (treat-all):** NB = prevalencia − (1−prevalencia) × θ/(1−θ). "
            "Representa tratar a todos los pacientes sin discriminación.\n"
            "- **No-tratar (treat-none):** NB = 0 por definición. Representa no tratar a nadie.\n"
            "- **Modelo:** NB = TPR × prevalencia − FPR × (1−prevalencia) × θ/(1−θ).\n\n"
            "**θ (umbral de decisión clínica):** la probabilidad mínima de evento que justifica "
            "la intervención. Refleja el balance implícito entre los costes de falsos positivos "
            "y falsos negativos en la práctica clínica concreta.\n\n"
            "**El modelo 'domina'** cuando su NB supera al de ambas estrategias de referencia "
            "en el θ evaluado. El **rango útil** es el conjunto de valores de θ en los que el "
            "modelo genera más NB que las alternativas.\n\n"
            "**`use_model`:** el modelo genera beneficio neto positivo y supera las alternativas en θ. "
            "**`do_not_use_model`:** el modelo no supera ninguna alternativa en el θ de referencia. "
            "**`restrict_to_threshold_range`:** el modelo es útil solo en un subconjunto del rango evaluado."
        )

    col_form, col_result = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("#### Parámetros del modelo")
        patient_id = st.text_input("patient_id", value="PAC-003", key="dca_pid")

        c1, c2 = st.columns(2)
        with c1:
            tp_rate = st.slider(
                "Sensibilidad del modelo (TPR)",
                0.01, 0.99, 0.82, 0.01,
                help="Tasa de verdaderos positivos del modelo diagnóstico.",
            )
            prevalence = st.slider(
                "Prevalencia del evento",
                0.01, 0.99, 0.20, 0.01,
                help="Prevalencia del diagnóstico/evento en la población de interés.",
            )
        with c2:
            fp_rate = st.slider(
                "FPR del modelo (1 − especificidad)",
                0.01, 0.99, 0.18, 0.01,
                help="Tasa de falsos positivos = 1 − especificidad.",
            )
            theta = st.slider(
                "θ — umbral de decisión clínica de referencia",
                0.01, 0.99, 0.15, 0.01,
                help="Probabilidad mínima del evento que justifica la intervención. "
                     "Refleja el balance coste/beneficio clínico para este umbral específico.",
            )

        st.markdown("#### Rango de umbrales θ a evaluar en la curva")
        theta_range = st.slider(
            "Rango de θ [lo, hi]",
            0.01, 0.99, (0.05, 0.50), 0.01,
            help="El sistema calcula el NB del modelo y las alternativas para cada θ en este rango.",
        )

        st.markdown("")
        run_btn = st.button("▶️ Ejecutar DCA", type="primary", use_container_width=True)

    with col_result:
        st.markdown("#### Resultado")
        if run_btn:
            payload = {
                "patient_id": patient_id.strip() or "PAC-003",
                "module": "dca",
                "inputs": {
                    "tp_rate": tp_rate,
                    "fp_rate": fp_rate,
                    "prevalence": prevalence,
                    "theta": theta,
                    "theta_range": list(theta_range),
                },
                "constraints": {},
                "version": SCHEMA_VERSION,
            }
            with st.spinner("Calculando DCA..."):
                output = _run(payload)

            if not _is_ok(output):
                render_blocked_error(output)
            else:
                render_action_badge(output["action"])
                render_audit_fields(output)

                result = output.get("result", {})
                nb = output.get("NB", {})

                render_metric_row([
                    ("NB(modelo) en θ", result.get("nb_at_theta")),
                    ("NB(tratar-todos) en θ", result.get("nb_treat_all_at_theta")),
                    ("NB(no-tratar) = 0", result.get("nb_treat_none", 0.0)),
                    ("Umbrales θ con NB(modelo) > alternativas", result.get("n_useful_thetas")),
                ])

                ur = result.get("useful_theta_range")
                if ur:
                    st.success(
                        f"**Rango útil del modelo:** θ ∈ [{ur[0]:.3f}, {ur[1]:.3f}] — "
                        "el modelo genera más beneficio neto que tratar-todos y no-tratar en este intervalo"
                    )
                else:
                    st.error(
                        "**Sin rango útil:** el modelo no supera ninguna estrategia alternativa "
                        "en ningún valor de θ del rango evaluado."
                    )

                dom = result.get("model_dominates_at_reference_theta")
                if dom:
                    st.success(
                        f"✅ El modelo genera más beneficio neto que tratar-todos y no-tratar "
                        f"en el umbral de referencia θ = {theta}"
                    )
                else:
                    st.warning(
                        f"⚠️ El modelo NO supera las estrategias alternativas en θ = {theta}"
                    )

                # Curva NB
                curve_model = result.get("curve_model", [])
                curve_all = result.get("curve_treat_all", [])
                if curve_model and curve_all:
                    st.markdown("**Curva de beneficio neto NB(θ)**")
                    st.caption(
                        "Eje X: umbral de probabilidad θ. "
                        "Eje Y: beneficio neto (NB). "
                        "El modelo es clínicamente útil donde su NB supera al de ambas estrategias de referencia."
                    )
                    try:
                        import pandas as pd
                        df_m = pd.DataFrame(curve_model).rename(
                            columns={"NB": "Modelo"}
                        ).set_index("theta")
                        df_a = pd.DataFrame(curve_all).rename(
                            columns={"NB": "Treat-all"}
                        ).set_index("theta")
                        df_chart = df_m.join(df_a)
                        df_chart["Treat-none"] = 0.0
                        st.line_chart(df_chart, use_container_width=True)
                    except Exception:
                        st.caption("(gráfico no disponible — pandas requerido)")

                render_explain(output.get("explain", ""))
                render_raw_json(output)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: PK / TDM
# ─────────────────────────────────────────────────────────────────────────────

_PK_MODES = {
    # ── v1 (sin cambios) ──────────────────────────────────────────────────────
    "iv_bolus":              "IV Bolus — C(t) = D/Vd · exp(−k·t)",
    "iv_infusion":           "IV Infusión — C(t) = R₀/CL · (1−exp(−k·t))",
    "multiple_dosing":       "Dosis múltiples — Cmax_ss / Cmin_ss",
    "oral_bateman":          "Oral Bateman — F·D·Ka / [Vd·(Ka−k)]",
    "target_dosing":         "Target Dosing — LD / MD para Css objetivo",
    "phenytoin_mm":          "Fenitoína MM — Michaelis–Menten paso a paso",
    "renal_adjustment":      "Ajuste renal — proporcional por CLCr",
    # ── v2 (nuevos) ───────────────────────────────────────────────────────────
    "cockcroft_gault":       "▶ v2 — Cockcroft-Gault: estimación de CLCr",
    "target_dosing_renal":   "▶ v2 — Target Dosing + ajuste renal automático",
    "tdm_bayes_map":         "▶ v2 — TDM Bayes-MAP básico (1C, sin MCMC)",
}


def _pk_form_inputs(mode: str) -> dict[str, Any]:
    """Renderiza los campos de formulario según el modo PK. Devuelve el dict inputs."""
    inp: dict[str, Any] = {"mode": mode}

    if mode == "iv_bolus":
        c1, c2, c3, c4 = st.columns(4)
        with c1: inp["dose_mg"]  = st.number_input("Dosis (mg)", 0.1, 5000.0, 500.0, 10.0)
        with c2: inp["vd_L"]     = st.number_input("Vd (L)", 0.1, 500.0, 30.0, 1.0)
        with c3: inp["cl_L_h"]   = st.number_input("CL (L/h)", 0.01, 50.0, 3.5, 0.1)
        with c4: inp["time_h"]   = st.number_input("Tiempo (h)", 0.0, 240.0, 4.0, 0.5)

    elif mode == "iv_infusion":
        c1, c2, c3, c4 = st.columns(4)
        with c1: inp["rate_mg_h"] = st.number_input("Tasa (mg/h)", 0.01, 2000.0, 50.0, 5.0)
        with c2: inp["cl_L_h"]    = st.number_input("CL (L/h)", 0.01, 50.0, 3.5, 0.1)
        with c3: inp["vd_L"]      = st.number_input("Vd (L)", 0.1, 500.0, 30.0, 1.0)
        with c4: inp["time_h"]    = st.number_input("Tiempo (h)", 0.0, 240.0, 6.0, 0.5)

    elif mode == "multiple_dosing":
        c1, c2, c3, c4 = st.columns(4)
        with c1: inp["dose_mg"]  = st.number_input("Dosis (mg)", 0.1, 5000.0, 100.0, 10.0)
        with c2: inp["tau_h"]    = st.number_input("τ intervalo (h)", 0.5, 48.0, 8.0, 0.5)
        with c3: inp["cl_L_h"]   = st.number_input("CL (L/h)", 0.01, 50.0, 5.0, 0.1)
        with c4: inp["vd_L"]     = st.number_input("Vd (L)", 0.1, 500.0, 50.0, 1.0)
        c5, c6, c7 = st.columns(3)
        with c5: inp["time_h"]   = st.number_input("Tiempo en intervalo (h)", 0.0, 48.0, 0.0, 0.5)
        with c6: inp["F"]        = st.number_input("F biodisponibilidad", 0.01, 1.0, 1.0, 0.01)
        with c7:
            _route_opts = {"IV (intravenosa)": "iv", "Oral": "oral"}
            inp["route"] = _route_opts[st.selectbox("Vía de administración", list(_route_opts.keys()))]

    elif mode == "oral_bateman":
        c1, c2, c3 = st.columns(3)
        with c1: inp["dose_mg"] = st.number_input("Dosis (mg)", 0.1, 5000.0, 250.0, 10.0)
        with c2: inp["F"]       = st.number_input("F biodisponibilidad", 0.01, 1.0, 0.85, 0.01)
        with c3: inp["ka_h"]    = st.number_input("Ka (h⁻¹)", 0.01, 20.0, 1.2, 0.1)
        c4, c5, c6 = st.columns(3)
        with c4: inp["cl_L_h"]  = st.number_input("CL (L/h)", 0.01, 50.0, 5.0, 0.1)
        with c5: inp["vd_L"]    = st.number_input("Vd (L)", 0.1, 500.0, 40.0, 1.0)
        with c6: inp["time_h"]  = st.number_input("Tiempo (h)", 0.0, 120.0, 2.0, 0.5)

    elif mode == "target_dosing":
        c1, c2, c3 = st.columns(3)
        with c1: inp["target_css_mg_L"] = st.number_input("Css objetivo (mg/L)", 0.01, 200.0, 15.0, 0.5)
        with c2: inp["cl_L_h"]          = st.number_input("CL (L/h)", 0.01, 50.0, 3.5, 0.1)
        with c3: inp["vd_L"]            = st.number_input("Vd (L)", 0.1, 500.0, 30.0, 1.0)
        c4, c5 = st.columns(2)
        with c4:
            inp["tau_h"] = st.number_input("τ intervalo (h)", 0.5, 48.0, 8.0, 0.5)
            inp["F"]     = st.number_input("F biodisponibilidad", 0.01, 1.0, 1.0, 0.01)
        with c5:
            tw = st.slider("Ventana terapéutica (mg/L)", 0.0, 100.0, (10.0, 20.0), 0.5)
            inp["therapeutic_window"] = list(tw)
        _calc_opts = {
            "Ambas — carga y mantenimiento": "both",
            "Solo dosis de carga (LD)":       "loading",
            "Solo dosis de mantenimiento (MD)": "maintenance",
        }
        inp["calc_type"] = _calc_opts[st.selectbox("Calcular", list(_calc_opts.keys()))]

    elif mode == "phenytoin_mm":
        c1, c2, c3 = st.columns(3)
        with c1: inp["vmax_mg_day"]        = st.number_input("Vmax (mg/día)", 10.0, 2000.0, 500.0, 10.0)
        with c2: inp["km_mg_L"]            = st.number_input("Km (mg/L)", 0.1, 50.0, 4.0, 0.1)
        with c3: inp["dose_guess_mg_day"]  = st.number_input("Dosis inicial (mg/día)", 10.0, 2000.0, 300.0, 10.0)
        c4, c5 = st.columns(2)
        with c4:
            tr = st.slider("Ventana terapéutica (mg/L)", 0.0, 60.0, (10.0, 20.0), 0.5)
            inp["target_range_mg_L"] = list(tr)
        with c5:
            inp["vd_L"]    = st.number_input("Vd (L)", 1.0, 200.0, 50.0, 1.0)
            inp["c0_mg_L"] = st.number_input("C₀ inicial (mg/L)", 0.0, 50.0, 0.0, 0.5)
        inp["dt_h"]    = st.number_input("Paso integración (h)", 0.1, 4.0, 1.0, 0.1)
        inp["max_days"] = st.number_input("Días máximos", 1.0, 60.0, 30.0, 1.0)

    elif mode == "renal_adjustment":
        c1, c2, c3 = st.columns(3)
        with c1: inp["standard_dose_mg"]      = st.number_input("Dosis estándar (mg)", 0.1, 5000.0, 500.0, 10.0)
        with c2: inp["clcr_patient_mL_min"]   = st.number_input("CLCr paciente (mL/min)", 0.0, 200.0, 50.0, 1.0)
        with c3: inp["clcr_ref_mL_min"]       = st.number_input("CLCr referencia (mL/min)", 1.0, 200.0, 100.0, 1.0)

    # ── v2: Cockcroft-Gault ───────────────────────────────────────────────────
    elif mode == "cockcroft_gault":
        st.caption(
            "Calcula el aclaramiento de creatinina (CLCr) por Cockcroft-Gault. "
            "Válido en adultos con función renal estable. "
            "No usar en pediatría, embarazo ni obesidad mórbida sin ajuste de peso."
        )
        c1, c2 = st.columns(2)
        with c1:
            inp["age"]  = st.number_input("Edad (años)", 18, 120, 65, 1)
            inp["weight_kg"] = st.number_input("Peso corporal (kg)", 20.0, 250.0, 70.0, 0.5)
        with c2:
            _sex_opts = {"Masculino (M)": "M", "Femenino (F)": "F"}
            inp["sex"] = _sex_opts[st.selectbox("Sexo", list(_sex_opts.keys()))]
            inp["serum_creatinine_mg_dL"] = st.number_input(
                "Creatinina sérica (mg/dL)", 0.1, 20.0, 1.2, 0.1,
                help="Creatinina en estado estable. Valores muy bajos pueden sobreestimar CLCr."
            )

    # ── v2: Target Dosing con ajuste renal automático ─────────────────────────
    elif mode == "target_dosing_renal":
        st.caption(
            "Calcula CLCr por Cockcroft-Gault y ajusta el CL del fármaco proporcionalmente. "
            "**Simplificación:** CL_adj = CL_base × (CLCr_pac / CLCr_ref). "
            "No es modelo poblacional. Verificar con niveles séricos."
        )
        st.markdown("**Datos del paciente (para Cockcroft-Gault)**")
        c1, c2, c3, c4 = st.columns(4)
        with c1: inp["age"]  = st.number_input("Edad (años)", 18, 120, 68, 1)
        with c2:
            _sex_opts2 = {"Masculino (M)": "M", "Femenino (F)": "F"}
            inp["sex"] = _sex_opts2[st.selectbox("Sexo", list(_sex_opts2.keys()), key="tdr_sex")]
        with c3: inp["weight_kg"] = st.number_input("Peso (kg)", 20.0, 250.0, 70.0, 0.5, key="tdr_wt")
        with c4: inp["serum_creatinine_mg_dL"] = st.number_input("Creatinina (mg/dL)", 0.1, 20.0, 1.4, 0.1, key="tdr_cr")

        st.markdown("**Parámetros del fármaco**")
        c5, c6, c7 = st.columns(3)
        with c5:
            inp["base_cl_L_h"]                = st.number_input("CL base (L/h)", 0.01, 50.0, 3.5, 0.1,
                                                help="CL poblacional para el CLCr de referencia")
            inp["drug_clcr_reference_mL_min"] = st.number_input("CLCr de referencia (mL/min)", 1.0, 200.0, 100.0, 5.0,
                                                help="CLCr para el que está definido el CL base")
        with c6:
            inp["vd_L"]  = st.number_input("Vd (L)", 0.1, 500.0, 30.0, 1.0, key="tdr_vd")
            inp["tau_h"] = st.number_input("τ intervalo (h)", 0.5, 48.0, 12.0, 0.5, key="tdr_tau")
        with c7:
            inp["F"]               = st.number_input("F biodisponibilidad", 0.01, 1.0, 1.0, 0.01, key="tdr_F")
            inp["target_css_mg_L"] = st.number_input("Css objetivo (mg/L)", 0.01, 200.0, 15.0, 0.5)
        tw2 = st.slider("Ventana terapéutica (mg/L)", 0.0, 100.0, (10.0, 20.0), 0.5, key="tdr_tw")
        inp["therapeutic_window"] = list(tw2)
        _calc_opts2 = {
            "Ambas — carga y mantenimiento": "both",
            "Solo dosis de carga (LD)":       "loading",
            "Solo dosis de mantenimiento (MD)": "maintenance",
        }
        inp["calc_type"] = _calc_opts2[st.selectbox("Calcular", list(_calc_opts2.keys()), key="tdr_calc")]

    # ── v2: TDM Bayes-MAP ─────────────────────────────────────────────────────
    elif mode == "tdm_bayes_map":
        st.caption(
            "Estimación MAP básica para 1 compartimento. "
            "Supone steady-state. Priors log-normales. Optimización por sección dorada (sin MCMC). "
            "Orientativo — no sustituye TDM clínico validado."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            inp["dose_mg"] = st.number_input("Dosis por intervalo (mg)", 0.1, 5000.0, 1000.0, 50.0)
            inp["tau_h"]   = st.number_input("τ intervalo (h)", 0.5, 48.0, 12.0, 0.5, key="map_tau")
        with c2:
            _route_map = {"IV (intravenosa)": "iv", "Oral": "oral"}
            inp["route"] = _route_map[st.selectbox("Vía", list(_route_map.keys()), key="map_route")]
            inp["F"]     = st.number_input("F biodisponibilidad", 0.01, 1.0, 1.0, 0.01, key="map_F")
        with c3:
            inp["sigma_obs_mg_L"] = st.number_input(
                "Error observación σ (mg/L)", 0.1, 20.0, 2.0, 0.1,
                help="Incertidumbre asumida en las concentraciones observadas"
            )
            inp["optimize_vd"] = st.checkbox(
                "Optimizar Vd también (descenso coordenado 2D)",
                value=False,
                help="Si activo: optimiza CL y Vd conjuntamente. Si no: Vd fijo en el prior."
            )

        st.markdown("**Prior poblacional del fármaco**")
        cp1, cp2, cp3, cp4 = st.columns(4)
        with cp1: inp["prior_cl_mean_L_h"] = st.number_input("CL prior — media (L/h)", 0.01, 50.0, 3.5, 0.1)
        with cp2: inp["prior_cl_sd_L_h"]   = st.number_input("CL prior — DE (L/h)", 0.01, 20.0, 1.5, 0.1)
        with cp3: inp["prior_vd_mean_L"]   = st.number_input("Vd prior — media (L)", 0.1, 500.0, 30.0, 1.0)
        with cp4: inp["prior_vd_sd_L"]     = st.number_input("Vd prior — DE (L)", 0.1, 200.0, 10.0, 1.0)

        st.markdown("**Concentraciones observadas (en estado estacionario)**")
        st.caption(
            "Ingrese al menos 1 concentración observada. "
            "Tiempo = horas post-última dosis en SS. "
            "Con 1 sola observación, el prior domina fuertemente la estimación."
        )
        n_obs = st.number_input("Número de observaciones", 1, 6, 2, 1)
        obs_list = []
        obs_cols = st.columns(min(int(n_obs), 3))
        for i in range(int(n_obs)):
            col_idx = i % 3
            with obs_cols[col_idx]:
                t_obs = st.number_input(f"Obs {i+1} — tiempo (h)", 0.0, 48.0, float(i * 4 + 2), 0.5, key=f"obs_t_{i}")
                c_obs = st.number_input(f"Obs {i+1} — concentración (mg/L)", 0.0, 200.0, 12.0, 0.5, key=f"obs_c_{i}")
                obs_list.append({"time_h": t_obs, "conc_mg_L": c_obs})
        inp["observed_concentrations"] = obs_list

    return inp


def page_pk_tdm() -> None:
    section_header("💊 PK / TDM Core v2.0",
                   "Farmacocinética monocompartimental — Monitoreo Terapéutico de Fármacos")
    warning_prototype()

    st.caption(
        "Modelo 1C lineal. Todos los outputs son orientativos — requieren confirmación con niveles séricos reales. "
        "v2 añade: Cockcroft-Gault, ajuste renal automático y Bayes-MAP básico (sin MCMC)."
    )

    with st.expander("¿Cómo interpretar este módulo?", expanded=False):
        st.markdown(
            "**PK/TDM Core v2.0** implementa cálculo farmacocinético con el modelo "
            "monocompartimental (1C) lineal. Cada modo resuelve un problema específico:\n\n"
            "**Modos v1 (sin cambios):**\n"
            "- **IV Bolus / IV Infusión / Dosis múltiples / Oral Bateman:** simulación de la "
            "concentración plasmática en función del tiempo para distintas vías y esquemas de administración.\n"
            "- **Target Dosing:** cálculo inverso — dada una Css objetivo, estima LD y MD.\n"
            "- **Fenitoína Michaelis-Menten:** cinética no lineal, integración numérica Euler.\n"
            "- **Ajuste renal:** ajuste proporcional de dosis según CLCr ingresado manualmente.\n\n"
            "**Modos v2 (nuevos):**\n"
            "- **Cockcroft-Gault:** estima el aclaramiento de creatinina (CLCr) a partir de edad, "
            "sexo, peso y creatinina sérica. Válido en adultos con función renal estable.\n"
            "- **Target Dosing renal automático:** combina Cockcroft-Gault con target dosing — "
            "ajusta CL proporcionalmente (CL_adj = CL_base × CLCr_pac/CLCr_ref) y calcula LD/MD. "
            "Simplificación lineal explícita — no es modelo poblacional.\n"
            "- **TDM Bayes-MAP:** estima CL y Vd posteriores a partir de concentraciones observadas "
            "y un prior poblacional, usando optimización MAP básica (sección dorada, sin MCMC). "
            "Asume steady-state. Orientativo — no sustituye software TDM validado clínicamente.\n\n"
            "**Por qué la acción siempre es `review_dosing` en modos de dosificación:** "
            "Ningún cálculo PK/TDM de este módulo reemplaza la evaluación clínica, los niveles séricos "
            "reales ni el juicio farmacológico. El sistema nunca emite `start_treatment` para PK/TDM."
        )

    col_form, col_result = st.columns([1, 1], gap="large")

    with col_form:
        patient_id = st.text_input("patient_id", value="PK-001", key="pk_pid")
        mode = st.selectbox(
            "Modo de cálculo",
            options=list(_PK_MODES.keys()),
            format_func=lambda m: _PK_MODES[m],
        )
        st.markdown("#### Parámetros del modo")
        inp = _pk_form_inputs(mode)
        st.markdown("")
        run_btn = st.button("▶️ Ejecutar PK/TDM", type="primary", use_container_width=True)

    with col_result:
        st.markdown("#### Resultado")
        if run_btn:
            payload = {
                "patient_id": patient_id.strip() or "PK-001",
                "module": "pk_tdm",
                "inputs": inp,
                "constraints": {},
                "version": SCHEMA_VERSION,
            }
            with st.spinner("Calculando PK..."):
                output = _run(payload)

            if not _is_ok(output):
                render_blocked_error(output)
            else:
                render_action_badge(output["action"])
                render_audit_fields(output)

                result = output.get("result", {})

                # Métricas clave según modo
                if mode == "iv_bolus":
                    render_metric_row([
                        ("k (h⁻¹)", result.get("k_h")),
                        ("t½ (h)", result.get("t_half_h")),
                        ("C₀ (mg/L)", result.get("C0_mg_L")),
                        (f"C({result.get('time_h')}h) (mg/L)", result.get("Ct_mg_L")),
                    ])

                elif mode == "iv_infusion":
                    render_metric_row([
                        ("Css (mg/L)", result.get("Css_mg_L")),
                        (f"C(t) (mg/L)", result.get("Ct_mg_L")),
                        ("% Css", f"{result.get('frac_of_Css', 0)*100:.1f}%"),
                        ("t½ (h)", result.get("t_half_h")),
                    ])
                    st.caption(
                        f"90% Css a las {result.get('t90pct_Css_h')} h | "
                        f"95% Css a las {result.get('t95pct_Css_h')} h"
                    )

                elif mode == "multiple_dosing":
                    render_metric_row([
                        ("Cmax_ss (mg/L)", result.get("Cmax_ss_mg_L")),
                        ("Cmin_ss (mg/L)", result.get("Cmin_ss_mg_L")),
                        ("Factor acumulación", result.get("accumulation_factor")),
                        ("t½ (h)", result.get("t_half_h")),
                    ])
                    st.caption(result.get("warning", ""))

                elif mode == "oral_bateman":
                    degen = result.get("degenerate_case", False)
                    if degen:
                        st.warning("⚠️ Caso degenerado: ka ≈ k — solución límite aplicada.")
                    render_metric_row([
                        ("Tmax (h)", result.get("Tmax_h")),
                        ("Cmax (mg/L)", result.get("Cmax_mg_L")),
                        (f"C({result.get('time_h')}h) (mg/L)", result.get("Ct_mg_L")),
                        ("t½ (h)", result.get("t_half_h")),
                    ])

                elif mode == "target_dosing":
                    in_w = result.get("target_within_therapeutic_window")
                    if in_w is True:
                        st.success("✅ Target Css dentro de la ventana terapéutica simulada")
                    elif in_w is False:
                        st.error("❌ Target Css fuera de la ventana terapéutica")
                    metrics = []
                    if "loading_dose_mg" in result:
                        metrics.append(("LD (mg)", result["loading_dose_mg"]))
                    if "maintenance_dose_mg" in result:
                        metrics.append(("MD (mg/τ)", result["maintenance_dose_mg"]))
                    metrics += [
                        ("Css objetivo (mg/L)", result.get("target_Css_mg_L")),
                        ("t½ (h)", result.get("t_half_h")),
                    ]
                    render_metric_row(metrics)
                    st.caption(result.get("limitation", ""))

                elif mode == "phenytoin_mm":
                    converged = result.get("converged", False)
                    if converged:
                        st.success(
                            f"✅ Convergencia en {len(result.get('dose_trials', []))} ensayo(s). "
                            f"Css estimado: {result.get('Css_estimated_mg_L')} mg/L dentro de la ventana terapéutica."
                        )
                    else:
                        st.error(
                            "❌ Sin convergencia: el sistema no encontró una dosis que llevara la Css "
                            f"dentro de la ventana terapéutica en el número máximo de ensayos. "
                            f"Css al finalizar: {result.get('Css_estimated_mg_L')} mg/L. "
                            "Revisar parámetros Vmax/Km o ampliar el rango."
                        )
                    render_metric_row([
                        ("Dosis inicial (mg/día)", result.get("initial_dose_mg_day")),
                        ("Dosis final (mg/día)", result.get("final_dose_mg_day")),
                        ("Css estimado (mg/L)", result.get("Css_estimated_mg_L")),
                    ])
                    trials = result.get("dose_trials", [])
                    if trials:
                        st.markdown("**Ensayos iterativos de ajuste de dosis:**")
                        st.caption("Cada fila muestra una dosis probada y la Css estimada resultante por integración numérica (Euler).")
                        st.dataframe(trials, use_container_width=True, hide_index=True)
                    st.caption(result.get("warning", ""))

                elif mode == "renal_adjustment":
                    render_metric_row([
                        ("Dosis estándar (mg)", result.get("standard_dose_mg")),
                        ("Dosis ajustada (mg)", result.get("adjusted_dose_mg")),
                        ("Ratio ajuste", result.get("dose_ratio")),
                        ("CLCr paciente", result.get("clcr_patient_mL_min")),
                    ])
                    st.caption(result.get("limitation", ""))

                # ── v2: Cockcroft-Gault ────────────────────────────────────────
                elif mode == "cockcroft_gault":
                    clcr_val = result.get("clcr_mL_min")
                    render_metric_row([
                        ("CLCr estimado (mL/min)", clcr_val),
                        ("Edad (años)", result.get("age_years")),
                        ("Peso (kg)", result.get("weight_kg")),
                        ("Creatinina (mg/dL)", result.get("serum_creatinine_mg_dL")),
                    ])
                    interp = result.get("interpretation", "")
                    if clcr_val is not None:
                        if clcr_val >= 60:
                            st.success(f"✅ {interp}")
                        elif clcr_val >= 30:
                            st.warning(f"⚠️ {interp}")
                        else:
                            st.error(f"❌ {interp}")
                    st.caption(f"Fórmula: {result.get('formula', '')}")
                    st.caption(result.get("limitation", ""))

                # ── v2: Target Dosing renal automático ────────────────────────
                elif mode == "target_dosing_renal":
                    in_w = result.get("target_within_therapeutic_window")
                    if in_w is True:
                        st.success("✅ Css objetivo dentro de la ventana terapéutica")
                    elif in_w is False:
                        st.warning("⚠️ Css objetivo fuera de la ventana terapéutica")
                    render_metric_row([
                        ("CLCr paciente (mL/min)", result.get("clcr_patient_mL_min")),
                        ("CL base (L/h)", result.get("base_cl_L_h")),
                        ("CL ajustado (L/h)", result.get("cl_adjusted_L_h")),
                        ("Ratio CLCr", result.get("clcr_ratio")),
                    ])
                    metrics2 = []
                    if "loading_dose_mg" in result:
                        metrics2.append(("LD (mg)", result["loading_dose_mg"]))
                    if "maintenance_dose_mg" in result:
                        metrics2.append(("MD (mg/τ)", result["maintenance_dose_mg"]))
                    metrics2 += [
                        ("Css objetivo (mg/L)", result.get("target_Css_mg_L")),
                        ("t½ ajustada (h)", result.get("t_half_h")),
                    ]
                    render_metric_row(metrics2)
                    st.caption(f"Interpretación renal: {result.get('renal_interpretation', '')}")
                    st.caption(result.get("warning_simplification", ""))

                # ── v2: TDM Bayes-MAP ─────────────────────────────────────────
                elif mode == "tdm_bayes_map":
                    render_metric_row([
                        ("CL estimado MAP (L/h)", result.get("cl_estimated_L_h")),
                        ("Vd estimado MAP (L)", result.get("vd_estimated_L")),
                        ("t½ estimada (h)", result.get("t_half_estimated_h")),
                        ("Obs. usadas", result.get("observations_used")),
                    ])
                    render_metric_row([
                        ("Cmax_ss predicho (mg/L)", result.get("cmax_ss_predicted_mg_L")),
                        ("Cmin_ss predicho (mg/L)", result.get("cmin_ss_predicted_mg_L")),
                        ("Css media estimada (mg/L)", result.get("css_average_estimated_mg_L")),
                    ])
                    st.caption(f"Método: {result.get('optimization_method', '')}")
                    st.markdown("**Comparación observado vs. predicho:**")
                    preds = result.get("predicted_concentrations", [])
                    if preds:
                        st.dataframe(preds, use_container_width=True, hide_index=True)
                    st.info(result.get("dose_adjustment_suggestion", ""))
                    with st.expander("⚠️ ¿Cómo interpretar Bayes-MAP en este módulo?"):
                        st.markdown(
                            "**Qué es esta estimación:**  \n"
                            "El módulo calcula los parámetros (CL, Vd) que mejor explican las "
                            "concentraciones observadas *dadas* las concentraciones esperadas por el "
                            "prior poblacional. Es una estimación MAP (máximo a posteriori) básica.\n\n"
                            "**Qué NO es:**  \n"
                            "- No es un MCMC completo (no hay distribución posterior completa ni intervalos de credibilidad).\n"
                            "- No es equivalente a InsightRx, DoseMe, TCIWorks ni software TDM validado clínicamente.\n"
                            "- No incorpora modelos poblacionales específicos por fármaco ni variabilidad intraindividual.\n\n"
                            "**Cuándo el prior domina la estimación:**  \n"
                            "Con 1 sola observación, la estimación de CL y Vd puede estar mal identificada — "
                            "el prior aporta la mayor parte de la información. "
                            "Con 3+ observaciones bien distribuidas en el intervalo, la estimación es más robusta.\n\n"
                            "**Acción recomendada:**  \n"
                            "`review_dosing` — Usar como orientación para ajuste, siempre confirmar con "
                            "niveles séricos adicionales y criterio farmacológico clínico. "
                            "No tomar decisiones de dosificación solo con este resultado."
                        )
                    lims = result.get("limitations", [])
                    if lims:
                        with st.expander("Limitaciones técnicas del módulo Bayes-MAP"):
                            for lim in lims:
                                st.markdown(f"- {lim}")

                render_explain(output.get("explain", ""))

                with st.expander("🔍 Detalle técnico completo"):
                    st.json(result)

                render_raw_json(output)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: AUDITORÍA
# ─────────────────────────────────────────────────────────────────────────────

def page_auditoria() -> None:
    section_header("📋 Trazabilidad — Registro de Auditoría",
                   "Audit_Log_Provenance — JSONL con SHA-256 dual y UUID por solicitud")

    with st.expander("¿Qué registra el sistema y para qué sirve?", expanded=False):
        st.markdown(
            "Hipócrates registra cada solicitud ejecutada en un archivo JSONL con los siguientes "
            "campos de trazabilidad:\n\n"
            "- **`request_id` (UUID v4):** identificador único generado para cada ejecución. "
            "No expresa calidad ni gravedad del resultado. Sirve para vincular el output visible "
            "en pantalla con el registro persistente en el log. Es el enlace entre la respuesta "
            "clínica y su evidencia auditada.\n\n"
            "- **`sha256_input` — hash determinista de los inputs:** hash SHA-256 calculado sobre "
            "`{patient_id, module, inputs, version}` *sin timestamp*. Dos solicitudes con exactamente "
            "los mismos inputs producirán el mismo `sha256_input`. Permite detectar ejecuciones "
            "duplicadas, verificar reproducibilidad del cálculo e identificar si los inputs "
            "registrados corresponden a lo que el usuario introdujo.\n\n"
            "- **`sha256_event` — hash único del evento completo:** hash SHA-256 calculado sobre "
            "el evento completo incluyendo `timestamp` y `request_id`. Único por ejecución incluso "
            "con inputs idénticos. Garantiza la integridad del registro tal como fue emitido: "
            "cualquier modificación posterior del archivo alteraría este hash.\n\n"
            "- **Inputs registrados en auditoría:** los inputs exactos que recibió el sistema, "
            "tal como fueron validados. Permiten reproducir el cálculo externamente o verificar "
            "que el resultado corresponde a los datos introducidos.\n\n"
            "El log se escribe en `outputs/audit_log.jsonl`. Las solicitudes bloqueadas por "
            "el Units Gate también quedan registradas."
        )

    if not LOG_PATH.exists():
        st.warning("El log de auditoría no existe todavía. Ejecuta algún módulo primero.")
        return

    # Leer últimas N líneas
    n_show = st.slider("Mostrar últimos N registros", 1, 50, 10)

    try:
        lines = LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        total = len(lines)
        recent = lines[-n_show:]
        records = [json.loads(l) for l in recent]
    except Exception as exc:
        st.error(f"Error leyendo log: {exc}")
        return

    st.caption(f"Total de registros en log: **{total}** | Mostrando los últimos {len(records)}")
    st.markdown("---")

    for i, rec in enumerate(reversed(records)):
        with st.expander(
            f"#{total - i} · {rec.get('module', '—')} · "
            f"{rec.get('patient_id', '—')} · "
            f"{rec.get('timestamp', '—')[:19].replace('T', ' ')}",
            expanded=(i == 0),
        ):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input(
                    "ID de solicitud (request_id)",
                    value=rec.get("request_id", "—"),
                    disabled=True, key=f"rid_{i}",
                    help="UUID único de esta ejecución. Vincula el output con su registro auditado.",
                )
                st.text_input("Módulo", value=rec.get("module", "—"),
                              disabled=True, key=f"mod_{i}")
                st.text_input("patient_id", value=rec.get("patient_id", "—"),
                              disabled=True, key=f"pid_{i}")
            with c2:
                st.text_input(
                    "sha256_input — hash determinista de inputs",
                    value=rec.get("sha256_input", rec.get("sha256", "—")),
                    disabled=True, key=f"h1_{i}",
                    help="SHA-256 sobre {patient_id, module, inputs, version} sin timestamp. "
                         "Reproducible: mismos inputs → mismo hash.",
                )
                st.text_input(
                    "sha256_event — hash único del evento",
                    value=rec.get("sha256_event", "—"),
                    disabled=True, key=f"h2_{i}",
                    help="SHA-256 sobre el evento completo incluyendo timestamp y request_id. "
                         "Único por ejecución. Garantiza integridad del registro.",
                )
                st.text_input("Timestamp", value=rec.get("timestamp", "—"),
                              disabled=True, key=f"ts_{i}")

            with st.expander("Inputs incluidos en el registro de auditoría"):
                st.caption("Inputs exactos que recibió el sistema para esta solicitud.")
                st.json(rec.get("inputs", {}))

    st.markdown("---")
    st.caption(f"Log: `{LOG_PATH}`")


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: SEPSIS PROTOCOL ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def page_sepsis() -> None:  # noqa: C901
    section_header(
        "🔴 Sepsis — Protocolo Computacional de Apoyo",
        "Estratificación de severidad · qSOFA · SOFA parcial · Bundle de alto nivel",
    )
    warning_prototype()

    with st.expander("¿Cómo interpretar este módulo?", expanded=False):
        st.markdown(
            "**Sepsis_Protocol_Engine** es un módulo de apoyo computacional para la "
            "estratificación de sospecha de sepsis basado en criterios Sepsis-3 "
            "(Singer 2016, JAMA) adaptados para computabilidad parcial.\n\n"
            "**Lo que calcula:**\n"
            "- **qSOFA** (0–3 puntos): screening rápido de disfunción orgánica con "
            "frecuencia respiratoria, presión sistólica y estado mental.\n"
            "- **SOFA parcial**: solo los componentes para los que haya datos disponibles "
            "(renal-creatinina, hepático-bilirrubina, coagulación-plaquetas, "
            "respiratorio-PaO2/FiO2). Declara explícitamente qué componentes se evaluaron.\n"
            "- **Lactato**: clasifica el nivel y genera flags de hipoperfusión tisular.\n"
            "- **MAP y vasopresor**: criterio hemodinámico de choque.\n"
            "- **Clase de severidad**: `Sospecha baja`, `Sepsis probable` o "
            "`Choque séptico probable`.\n"
            "- **Bundle de acciones de alto nivel**: qué hacer ahora, sin antibióticos "
            "específicos ni dosis.\n"
            "- **Tiempo de revaloración recomendado**.\n\n"
            "**Lo que NO hace:**\n"
            "- No prescribe antibióticos específicos ni dosis.\n"
            "- No evalúa germen ni resistencias.\n"
            "- No calcula SOFA cardiovascular formal ni GCS.\n"
            "- No incorpora respuesta a fluidos ni evaluación hemodinámica invasiva.\n"
            "- No reemplaza la evaluación clínica directa.\n\n"
            "**Acción `Iniciar manejo clínico` (`start_treatment`):**  \n"
            "Significa que el output computacional apoya iniciar manejo clínico inmediato "
            "según el bundle sugerido. **No es una orden autónoma.** La decisión final "
            "siempre recae en el clínico responsable."
        )

    col_form, col_result = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("#### Parámetros")

        patient_id = st.text_input(
            "ID del paciente",
            value="PAC-001",
            key="sepsis_pid",
            help="Identificador del paciente para trazabilidad.",
        )

        st.markdown("##### Parámetros obligatorios")

        suspected_infection = st.checkbox(
            "Sospecha clínica de infección",
            value=True,
            key="sepsis_inf",
            help="¿Hay sospecha clínica documentada de infección como causa del cuadro?",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            rr = st.number_input(
                "Frecuencia respiratoria (rpm)",
                min_value=1, max_value=60, value=18, step=1,
                key="sepsis_rr",
                help="Frecuencia respiratoria en respiraciones por minuto. "
                     "qSOFA: ≥ 22 rpm suma 1 punto.",
            )
            sbp = st.number_input(
                "Presión arterial sistólica (mmHg)",
                min_value=40, max_value=220, value=120, step=1,
                key="sepsis_sbp",
                help="Presión sistólica. qSOFA: ≤ 100 mmHg suma 1 punto.",
            )
        with col_b:
            map_mmhg = st.number_input(
                "Presión arterial media — MAP (mmHg)",
                min_value=10, max_value=160, value=85, step=1,
                key="sepsis_map",
                help="MAP < 65 mmHg es criterio hemodinámico de choque séptico.",
            )
            lactate = st.number_input(
                "Lactato sérico (mmol/L)",
                min_value=0.0, max_value=25.0, value=1.0, step=0.1, format="%.1f",
                key="sepsis_lac",
                help="Lactato ≥ 2.0 mmol/L: hipoperfusión. "
                     "Criterio metabólico de choque séptico (Sepsis-3).",
            )

        mental_status = st.checkbox(
            "Alteración del estado mental",
            value=False,
            key="sepsis_ms",
            help="Confusión, obnubilación, agitación o cualquier cambio del nivel de consciencia "
                 "respecto al basal. qSOFA: si presente, suma 1 punto.",
        )
        vasopressor = st.checkbox(
            "Soporte vasopresor activo",
            value=False,
            key="sepsis_vaso",
            help="¿El paciente recibe vasopresores (ej. norepinefrina) para mantener la presión?",
        )

        st.markdown("##### Parámetros opcionales")
        st.caption(
            "Los datos opcionales mejoran el SOFA parcial y los flags de hipoperfusión. "
            "El módulo funciona con solo los obligatorios."
        )

        with st.expander("Diuresis y función renal", expanded=False):
            urine_present = st.checkbox(
                "Diuresis disponible", value=False, key="sepsis_urine_chk"
            )
            urine_val = None
            if urine_present:
                urine_val = st.number_input(
                    "Diuresis (mL/kg/h)",
                    min_value=0.0, max_value=10.0, value=0.7, step=0.05, format="%.2f",
                    key="sepsis_urine",
                    help="Oliguria: < 0.5 mL/kg/h. Señal de hipoperfusión renal.",
                )
            creatinine_present = st.checkbox(
                "Creatinina disponible", value=False, key="sepsis_cr_chk"
            )
            creatinine_val = None
            if creatinine_present:
                creatinine_val = st.number_input(
                    "Creatinina (mg/dL)",
                    min_value=0.0, max_value=20.0, value=1.0, step=0.1, format="%.1f",
                    key="sepsis_cr",
                    help="Componente renal del SOFA. SOFA renal ≥ 1: ≥ 1.2 mg/dL.",
                )

        with st.expander("Función hepática y coagulación", expanded=False):
            bilirubin_present = st.checkbox(
                "Bilirrubina disponible", value=False, key="sepsis_bil_chk"
            )
            bilirubin_val = None
            if bilirubin_present:
                bilirubin_val = st.number_input(
                    "Bilirrubina total (mg/dL)",
                    min_value=0.0, max_value=40.0, value=0.8, step=0.1, format="%.1f",
                    key="sepsis_bil",
                    help="Componente hepático del SOFA. SOFA hep ≥ 1: ≥ 1.2 mg/dL.",
                )
            platelets_present = st.checkbox(
                "Plaquetas disponibles", value=False, key="sepsis_plt_chk"
            )
            platelets_val = None
            if platelets_present:
                platelets_val = st.number_input(
                    "Plaquetas (×10³/μL)",
                    min_value=1, max_value=1000, value=200, step=5,
                    key="sepsis_plt",
                    help="Componente coagulación SOFA. SOFA coag ≥ 1: < 150 k/μL.",
                )

        with st.expander("Función respiratoria", expanded=False):
            pao2_present = st.checkbox(
                "PaO2/FiO2 disponible", value=False, key="sepsis_pf_chk"
            )
            pao2_val = None
            if pao2_present:
                pao2_val = st.number_input(
                    "Índice PaO2/FiO2 (mmHg)",
                    min_value=1, max_value=600, value=400, step=10,
                    key="sepsis_pf",
                    help="Componente respiratorio SOFA. Valores < 300 indican disfunción.",
                )
            mech_vent = st.checkbox(
                "Ventilación mecánica activa",
                value=False, key="sepsis_vm",
                help="Necesario para SOFA respiratorio grados 3-4 (PaO2/FiO2 < 200 con VM).",
            )

        st.markdown("")
        run_btn = st.button(
            "▶️ Calcular protocolo de sepsis",
            type="primary",
            use_container_width=True,
        )

    with col_result:
        st.markdown("#### Resultado")

        if run_btn:
            inputs_payload: dict[str, Any] = {
                "suspected_infection": suspected_infection,
                "rr": rr,
                "sbp": sbp,
                "mental_status_altered": mental_status,
                "map_mmHg": float(map_mmhg),
                "lactate_mmol_L": float(lactate),
                "vasopressor": vasopressor,
            }
            if urine_present and urine_val is not None:
                inputs_payload["urine_output_ml_kg_h"] = float(urine_val)
            if creatinine_present and creatinine_val is not None:
                inputs_payload["creatinine_mg_dL"] = float(creatinine_val)
            if bilirubin_present and bilirubin_val is not None:
                inputs_payload["bilirubin_mg_dL"] = float(bilirubin_val)
            if platelets_present and platelets_val is not None:
                inputs_payload["platelets_k_uL"] = float(platelets_val)
            if pao2_present and pao2_val is not None:
                inputs_payload["pao2_fio2"] = float(pao2_val)
            if mech_vent:
                inputs_payload["mechanical_ventilation"] = True

            payload = {
                "patient_id": patient_id.strip() or "PAC-001",
                "module": "sepsis_protocol",
                "inputs": inputs_payload,
                "constraints": {},
                "version": SCHEMA_VERSION,
            }

            with st.spinner("Evaluando protocolo de sepsis..."):
                output = _run(payload)

            if not _is_ok(output):
                render_blocked_error(output)
            else:
                result = output.get("result", {})
                severity = result.get("severity_class", "")

                # ── Clase de severidad ──────────────────────────────────────
                severity_label = humanize_severity_class(severity)
                if severity == "septic_shock_probable":
                    st.error(f"🔴 **{severity_label}**")
                elif severity == "sepsis_probable":
                    st.warning(f"🟠 **{severity_label}**")
                else:
                    st.info(f"🟢 **{severity_label}**")

                render_action_badge(output["action"])
                render_audit_fields(output)

                # ── qSOFA ───────────────────────────────────────────────────
                st.markdown("**qSOFA**")
                qsofa_score = result.get("qsofa_score", 0)
                qsofa_positive = result.get("qsofa_positive", False)
                qsofa_color = "🔴" if qsofa_positive else "🟢"
                st.metric(
                    label=f"qSOFA {qsofa_color}",
                    value=f"{qsofa_score} / 3",
                    help="qSOFA ≥ 2: screening positivo para disfunción orgánica (Sepsis-3).",
                )
                if result.get("qsofa_components"):
                    for comp in result["qsofa_components"]:
                        st.caption(f"  ✓ {comp}")
                st.caption(result.get("qsofa_interpretation", ""))

                st.markdown("---")

                # ── SOFA parcial ────────────────────────────────────────────
                st.markdown("**SOFA parcial**")
                sofa_score = result.get("sofa_partial_score", 0)
                sofa_n = result.get("sofa_n_components_evaluated", 0)
                if sofa_n == 0:
                    st.caption(
                        "Sin datos suficientes para calcular ningún componente de SOFA. "
                        "Proporcione creatinina, bilirrubina, plaquetas o PaO2/FiO2."
                    )
                else:
                    sofa_color = "🔴" if sofa_score >= 2 else "🟡" if sofa_score == 1 else "🟢"
                    st.metric(
                        label=f"SOFA parcial {sofa_color} ({sofa_n} componente(s))",
                        value=f"{sofa_score} pts",
                        help="SOFA ≥ 2 sugiere disfunción orgánica. "
                             "Solo componentes con datos disponibles.",
                    )
                    for det in result.get("sofa_component_details", []):
                        st.caption(f"  • {det}")
                st.caption(result.get("sofa_interpretation", ""))

                st.markdown("---")

                # ── Lactato, MAP, Vasopresor ────────────────────────────────
                st.markdown("**Señales de hipoperfusión**")
                render_metric_row([
                    (
                        "Lactato (mmol/L)",
                        f"{result.get('lactate_mmol_l', '—'):.1f} — "
                        + humanize_lactate_level(result.get("lactate_level", "")),
                    ),
                    ("MAP (mmHg)", f"{result.get('map_mmhg', '—'):.1f}"),
                    ("Vasopresor", "Sí" if result.get("vasopressor") else "No"),
                    ("Hipoperfusión global", "Sí ⚠️" if result.get("hypoperfusion_flag") else "No"),
                ])
                if result.get("urine_output_detail"):
                    st.caption(f"Diuresis: {result['urine_output_detail']}")

                st.markdown("---")

                # ── Bundle ──────────────────────────────────────────────────
                bundle = result.get("bundle_actions", [])
                recheck = result.get("recheck_time_minutes")
                if bundle:
                    st.markdown(
                        f"**Acciones sugeridas de alto nivel** "
                        f"— Revaloración en **{recheck} min**"
                    )
                    st.caption(
                        "Orientación computacional de alto nivel. "
                        "No prescribe antibióticos ni dosis específicas. "
                        "Requiere valoración clínica directa."
                    )
                    for i, act in enumerate(bundle, 1):
                        st.markdown(f"{i}. {act}")

                st.markdown("---")

                # ── Razón del sistema ───────────────────────────────────────
                with st.expander("Razonamiento del sistema", expanded=False):
                    st.markdown(result.get("severity_reason", ""))
                    if result.get("criteria_positive"):
                        st.markdown("**Criterios positivos identificados:**")
                        for c in result["criteria_positive"]:
                            st.markdown(f"- {c}")
                    if result.get("warnings"):
                        st.markdown("**Advertencias:**")
                        for w in result["warnings"]:
                            st.warning(w)

                # ── Limitaciones ────────────────────────────────────────────
                with st.expander("Limitaciones de este módulo (v1)", expanded=False):
                    for lim in result.get("limitations", []):
                        st.markdown(f"- {lim}")

                render_explain(output.get("explain", ""))
                render_raw_json(output)


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

if page == "home":
    page_home()
elif page == "bayes":
    page_bayes()
elif page == "abg":
    page_abg()
elif page == "dca":
    page_dca()
elif page == "pk_tdm":
    page_pk_tdm()
elif page == "sepsis":
    page_sepsis()
elif page == "auditoria":
    page_auditoria()
