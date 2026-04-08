# Release Notes — Hipócrates v0.5.0

**Fecha:** 2026-04-08  
**Tag sugerido:** `v0.5.0`  
**Estado:** Primera snapshot pública — prototipo de investigación

---

## Descripción

Esta es la primera versión pública del motor Hipócrates. Representa el estado funcional completo del MVP: todos los módulos clínicos implementados, suite de tests verde, consola visual operativa y documentación técnica honesta.

**Este no es un sistema clínico validado. Es un prototipo computacional serio de investigación.**

---

## Qué contiene esta versión

### Módulos clínicos

- **Bayes_SPRT_Engine** — SPRT de Wald con parada temprana real
- **ABG_HH_Stewart_Engine** — Interpretación gasométrica formal (H-H + Stewart-Fencl aproximado)
- **DCA_Utility_Module** — Decision Curve Analysis con NB(θ) y rango útil
- **PK_TDM_Core v2** — 10 modos PK monocompartimental incluyendo Cockcroft-Gault, target dosing con ajuste renal y Bayes-MAP básico
- **Sepsis_Protocol_Engine v1** — Estratificación qSOFA/SOFA parcial/lactato/MAP basada en Sepsis-3

### Infraestructura

- `Clinical_IO_Schema`: validación de payload de entrada
- `Units_Validity_Gate v2`: validación de dominio físico y clínico
- `Audit_Log_Provenance`: registro JSONL con SHA-256 dual (`sha256_input` determinista + `sha256_event` por ejecución)
- `Hipocrates_Orchestrator`: pipeline único de entrada al sistema
- Consola visual Streamlit (demo local, no despliegue público)

### Tests

338 tests pytest — todos passing en Python 3.10 y 3.13.

---

## Instalación

```bash
cd hipocrates
pip install -e .
pip install -r requirements.txt
```

## Correr tests

```bash
python -m pytest tests/ -q
```

Resultado esperado: `338 passed`

## Correr ejemplos

```bash
python run_examples.py
```

## Consola visual

```bash
streamlit run app/streamlit_app.py
```

---

## Advertencias importantes

- **Sin validación clínica**: los cálculos implementan fórmulas estándar pero no han sido validados en poblaciones reales.
- **Sin despliegue de producción**: la consola Streamlit es una demo local. No existe frontend público.
- **Licencia MIT**: código publicado bajo MIT License. Ver archivo `LICENSE`.
- **Audit log local**: `outputs/audit_log.jsonl` se genera en ejecución y está excluido del repositorio.
- **Parámetros PK poblacionales**: sin individualización por fármaco ni conexión a laboratorio real.

---

## Limitaciones conocidas

- Bayes-MAP (PK_TDM): sin MCMC, sin intervalos de credibilidad formales (`ci = null`)
- SOFA: implementación parcial (sin SOFA cardiovascular formal ni GCS numérico)
- Cockcroft-Gault: válido en adultos con función renal estable; no validado en casos límite
- DCA: calcula sobre parámetros introducidos manualmente, no sobre datasets reales

---

## Archivos no incluidos en el repositorio (excluidos por .gitignore)

- `outputs/audit_log.jsonl` — log de auditoría generado en ejecución (contiene datos reales de corridas)
- `diagnostico_resultado.txt` — contiene rutas locales del sistema
- `__pycache__/`, `.pytest_cache/` — artefactos de ejecución
- `src/*.egg-info/` — artefactos de packaging
- `.streamlit/secrets.toml`, `.streamlit/credentials.toml` — credenciales (si existieran)
