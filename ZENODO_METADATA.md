# Metadata Zenodo — Hipócrates v0.5.0

Metadata lista para copiar y pegar en el formulario de Zenodo.
Generado: 2026-04-08.
Estado del depósito: PENDIENTE.

---

## Campos para el formulario de Zenodo

### 1. Tipo de recurso

```
Software
```

### 2. Título

```
Hipócrates — Motor de Apoyo Clínico Computable (SMNC-5+)
```

### 3. Autores / Creators

```
Pintor, Jules
```

> Afiliación institucional: PENDIENTE (completar por el autor si aplica)
> ORCID: PENDIENTE (completar por el autor si aplica — https://orcid.org)

### 4. Descripción breve (para el campo "Description" — versión corta)

```
Motor determinista de apoyo clínico computable basado en el Sistema Médico Núcleo Computable SMNC-5+. Implementa razonamiento bayesiano secuencial (SPRT), interpretación gasométrica ácido-base, análisis por curva de decisión (DCA), farmacocinética monocompartimental (10 modos) y estratificación de sepsis (Sepsis-3). Prototipo de investigación sin validación clínica en poblaciones reales.
```

### 5. Descripción larga (para el campo "Description" — versión completa)

```
Hipócrates es un motor determinista de apoyo clínico computable basado en el Sistema Médico Núcleo Computable SMNC-5+. El sistema implementa cinco módulos clínicos formales:

- Bayes_SPRT_Engine: razonamiento bayesiano secuencial mediante el Sequential Probability Ratio Test (SPRT) de Wald, con parada temprana real.
- ABG_HH_Stewart_Engine: interpretación gasométrica ácido-base completa usando Henderson-Hasselbalch con aproximación Stewart-Fencl.
- DCA_Utility_Module: análisis de utilidad clínica mediante Decision Curve Analysis (DCA), con cálculo de Net Benefit NB(θ) y rango de umbral útil.
- PK_TDM_Core v2: farmacocinética monocompartimental con 10 modos de cálculo, incluyendo Cockcroft-Gault, target dosing con ajuste renal automático y estimación MAP bayesiana básica (Bayes-MAP, 1 compartimento, priors log-normales, optimización por sección dorada).
- Sepsis_Protocol_Engine v1: estratificación computable de sepsis y shock séptico basada en criterios Sepsis-3 (qSOFA, SOFA parcial, lactato, MAP, vasopresor), con bundle de acciones y tiempo de revaloración canónico.

La infraestructura del sistema incluye: Clinical_IO_Schema (validación de payload de entrada), Units_Validity_Gate v2 (validación de dominio físico y clínico), Audit_Log_Provenance (registro JSONL con SHA-256 dual: sha256_input determinista + sha256_event por ejecución), e Hipocrates_Orchestrator como pipeline único de entrada. El sistema incluye además una consola visual local en Streamlit (demo local, no despliegue público).

La suite de tests comprende 338 tests pytest, verificados en Python 3.10 y 3.13.

ADVERTENCIA: Este sistema es un prototipo de investigación computable. No ha sido validado clínicamente en poblaciones reales ni en entornos hospitalarios. No está indicado para uso clínico autónomo. No reemplaza la evaluación médica directa. Los outputs son estimaciones computacionales que requieren interpretación por personal clínico competente.
```

### 6. Versión

```
0.5.0
```

### 7. Licencia

```
MIT License
```

> Identificador SPDX: MIT
> Archivo LICENSE presente en el repositorio.

### 8. Fecha de publicación

```
2026-04-08
```

> Fecha del release GitHub v0.5.0 y del tag.

### 9. Keywords

```
clinical decision support
pharmacokinetics
Bayesian inference
acid-base interpretation
sepsis
decision curve analysis
research prototype
computable medicine
SPRT
TDM
Sepsis-3
Stewart-Fencl
```

### 10. Notas de versión (campo "Version notes" o "Additional notes")

```
Primera snapshot pública del prototipo. Versión MVP con todos los módulos clínicos operativos.

Módulos incluidos: Bayes_SPRT_Engine v1, ABG_HH_Stewart_Engine v1, DCA_Utility_Module v1, PK_TDM_Core v2, Sepsis_Protocol_Engine v1, Clinical_IO_Schema v1, Units_Validity_Gate v2, Audit_Log_Provenance v1, Hipocrates_Orchestrator v1.

Módulos no incluidos en esta versión: Glucose_MPC_Controller, ERV_API_Connector, LUM_Diagnostic_Engine, Psychopathology_M1M2M3_Engine, despliegue en servidor, Docker, APIs externas, MCMC, PK multicompartimental, modelos poblacionales.

338 tests pytest pasando en Python 3.10 y 3.13.
```

### 11. Advertencia de uso / Disclaimer (campo "Notes" o "Additional notes")

```
Este sistema es un prototipo de investigación computable. Los cálculos implementan fórmulas estándar de la literatura médica pero no han sido validados en cohortes de pacientes reales ni han superado un proceso de validación clínica formal. No está indicado para toma de decisiones clínicas autónomas, diagnóstico, prescripción ni ningún uso clínico directo. Cualquier uso en entornos con pacientes reales requiere supervisión clínica experta y validación independiente.

Los outputs del sistema son estimaciones deterministas reproducibles, no diagnósticos ni recomendaciones terapéuticas.

El audit log (outputs/audit_log.jsonl) se genera en ejecución local y no está incluido en el depósito archivístico.
```

### 12. Identificadores relacionados (Related identifiers)

```
Tipo: GitHub release
URL: https://github.com/julespintor-tech/hipocrates/releases/tag/v0.5.0
Relación: isSupplementTo

Tipo: GitHub repository
URL: https://github.com/julespintor-tech/hipocrates
Relación: isSupplementTo
```

### 13. Lenguaje

```
Spanish / Español (spa)
```

> Nota: La documentación y la interfaz son principalmente en español. El código fuente y los tests mezclan inglés (identificadores, API) y español (comentarios internos, mensajes).

---

## Campos que quedan PENDIENTES

Los siguientes campos no han sido rellenados porque no existen en el repositorio ni pueden inferirse sin inventar. El autor debe completarlos antes del depósito:

| Campo | Estado | Acción requerida |
|-------|--------|-----------------|
| ORCID del autor | PENDIENTE | Registrarse en https://orcid.org si aplica |
| Afiliación institucional | PENDIENTE | Completar si aplica |
| Financiación / Funding | PENDIENTE | Completar si aplica (beca, proyecto, etc.) |
| DOI | PENDIENTE | Asignado automáticamente por Zenodo tras el depósito |
| Grant/Award number | PENDIENTE | Completar si aplica |

---

## Fuente de verdad del depósito

- Repositorio: https://github.com/julespintor-tech/hipocrates
- Release: https://github.com/julespintor-tech/hipocrates/releases/tag/v0.5.0
- Tag: v0.5.0 (commit 97acb51)
- Fecha del release: 2026-04-08
- Estado: release público publicado en GitHub ✓
