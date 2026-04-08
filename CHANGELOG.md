# Changelog — Hipócrates

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versiones siguiendo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0] — 2026-04-08

Primera snapshot pública del prototipo. Primer estado estable con todos los módulos del MVP operativos, suite de tests completa y consola visual funcional.

### Añadido

- **PK_TDM_Core v2**: tres modos nuevos sobre la base v1
  - `cockcroft_gault`: estimación de CLCr a partir de edad, sexo, peso y creatinina sérica
  - `target_dosing_renal`: target dosing con ajuste automático de CL por Cockcroft-Gault
  - `tdm_bayes_map`: estimación MAP básica de CL (y Vd opcional) a partir de niveles séricos observados — 1C, priors log-normales, optimización por sección dorada
- **Sepsis_Protocol_Engine v1**: estratificación computable de sepsis basada en Sepsis-3
  - qSOFA, SOFA parcial (renal, hepático, coagulación, respiratorio), lactato, MAP, vasopresor
  - Tres clases: `low_suspicion`, `sepsis_probable`, `septic_shock_probable`
  - Bundle de acciones y tiempo de revaloración canónico
- **Auditoría dual SHA-256**: `sha256_input` (determinista sobre payload) + `sha256_event` (único por ejecución)
- **Units Gate v2**: validación de dominio extendida para observaciones y priors PK/TDM v2
- **Consola visual Streamlit**: seis módulos con formularios dinámicos y panel de trazabilidad
- Suite de tests: 338 tests pytest (verificados en Python 3.10 y 3.13)
- 14 ejemplos JSON en `examples/`; `run_examples.py` ejecuta 13 casos con salida por consola
- `.streamlit/config.toml`: configuración reproducible para la consola visual

### Módulos presentes en esta versión

| Módulo | Versión | Estado |
|--------|---------|--------|
| `Clinical_IO_Schema` | v1 | Estable |
| `Units_Validity_Gate` | v2 | Estable |
| `Audit_Log_Provenance` | v1 | Estable |
| `Hipocrates_Orchestrator` | v1 | Estable |
| `Bayes_SPRT_Engine` | v1 | Estable |
| `ABG_HH_Stewart_Engine` | v1 | Estable |
| `DCA_Utility_Module` | v1 | Estable |
| `PK_TDM_Core` | v2 | Estable |
| `Sepsis_Protocol_Engine` | v1 | Estable |

### No incluido en esta versión

- `Glucose_MPC_Controller`
- `ERV_API_Connector` / `ERV_Review_Queue`
- `LUM_Diagnostic_Engine` / `Psychopathology_M1M2M3_Engine`
- Despliegue en servidor, Docker, APIs externas
- Validación clínica formal en poblaciones reales
- MCMC, PK multicompartimental, modelos poblacionales

---

## [0.1.0] — 2026-04-04

Versión inicial interna. MVP con módulos core: Bayes SPRT, ABG H-H/Stewart, DCA, PK/TDM Core v1 (7 modos), infraestructura de auditoría y orquestador.
