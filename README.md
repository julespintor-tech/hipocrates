# Hipócrates — Motor de Apoyo Clínico Computable

> **ADVERTENCIA:** Este sistema es un **prototipo de investigación y apoyo computacional**.
> No está validado para uso clínico autónomo. Los outputs son estimaciones computacionales
> que requieren interpretación por personal clínico competente.
> No reemplaza la evaluación médica directa ni incorpora el contexto clínico completo del paciente.

---

## Qué es Hipócrates

Hipócrates es un **motor determinista de apoyo clínico computable** basado en el **Sistema Médico Núcleo Computable SMNC-5+**. Implementa algoritmos formales de razonamiento bayesiano secuencial, interpretación gasométrica ácido-base, análisis de utilidad clínica por curva de decisión y cálculo farmacocinético monocompartimental, con salida estructurada homogénea, auditoría criptográfica integrada y validación de dominio estricta antes de cada cálculo.

No es un sistema de IA generativa ni un chatbot médico. Cada cálculo clínico es reproducible, auditable y formalmente verificable: dado el mismo payload de entrada, el sistema produce siempre el mismo resultado clínico y el mismo `sha256_input`. Los campos de trazabilidad por ejecución (`request_id`, timestamp, `sha256_event`) varían en cada corrida por diseño — garantizan unicidad del registro de auditoría, no identidad del cálculo.

---

## Qué incluye este MVP

| Módulo | Archivo | Función |
|--------|---------|---------|
| `Clinical_IO_Schema` | `core/io_schema.py` | Valida la estructura del payload de entrada antes de procesarlo |
| `Units_Validity_Gate` | `core/units_gate.py` | Rechaza ejecución si los inputs violan restricciones de dominio físico o clínico |
| `Audit_Log_Provenance` | `core/audit.py` | Registra cada solicitud con `sha256_input` + `sha256_event` + `request_id` en JSONL |
| `Bayes_SPRT_Engine` | `modules/bayes_sprt.py` | SPRT de Wald — actualización bayesiana secuencial con parada temprana real |
| `ABG_HH_Stewart_Engine` | `modules/abg_hh_stewart.py` | Interpretación gasométrica formal: H–H + aproximación Stewart-Fencl |
| `DCA_Utility_Module` | `modules/dca.py` | Decision Curve Analysis — beneficio neto por umbral de decisión clínica |
| `PK_TDM_Core v2` | `modules/pk_tdm.py` | Farmacocinética monocompartimental (1C) con 10 modos — ver detalle abajo |
| `Sepsis_Protocol_Engine` | `modules/sepsis_protocol.py` | Estratificación de sepsis: qSOFA, SOFA parcial, lactato, MAP, bundle — ver detalle abajo |
| `Hipocrates_Orchestrator` | `core/orchestrator.py` | Pipeline completo: schema → gate → módulo → auditoría |

### PK_TDM_Core v2.0 — Modos soportados

El módulo `pk_tdm` soporta 10 modos de operación, seleccionados con el campo `"mode"` dentro de `inputs`:

**Modos v1 (sin cambios, retrocompatibles):**

| Modo | Descripción | Fórmula principal |
|------|-------------|-------------------|
| `iv_bolus` | IV en bolo (1 compartimento) | C(t) = D/Vd · exp(−k·t) |
| `iv_infusion` | Infusión IV simple + estado estacionario | C(t) = R₀/CL · (1−exp(−k·t)); Css = R₀/CL |
| `multiple_dosing` | Dosis repetidas IV u oral; Cmax_ss, Cmin_ss | Factor acumulación R = 1/(1−exp(−k·τ)) |
| `oral_bateman` | Oral extravascular con ecuación de Bateman | C(t) = F·D·Ka/[Vd·(Ka−k)]·(exp(−kt)−exp(−Ka·t)) |
| `target_dosing` | Cálculo inverso: LD y/o MD para Css objetivo | LD = Css·Vd/F; MD = Css·CL·τ/F |
| `phenytoin_mm` | Cinética Michaelis–Menten fenitoína por integración numérica | dC/dt = D/Vd − Vmax·C/(Km+C) |
| `renal_adjustment` | Ajuste proporcional de dosis por CLCr dado manualmente | new_dose = std_dose × (CLCr_pat / CLCr_ref) |

**Modos v2 (nuevos en esta versión):**

| Modo | Descripción | Nota |
|------|-------------|------|
| `cockcroft_gault` | Estimación de CLCr a partir de edad, sexo, peso y creatinina sérica | Fórmula estándar CG; válida en adultos con función renal estable |
| `target_dosing_renal` | Target dosing con ajuste automático de CL por Cockcroft-Gault | CL_adj = CL_base × (CLCr_pac / CLCr_ref) — simplificación lineal explícita |
| `tdm_bayes_map` | Estimación MAP básica de CL (y Vd opcional) a partir de niveles séricos | 1C, SS, priors log-normales, optimización por sección dorada — sin MCMC |

**Lo que añade v2:**
- Cálculo automático de función renal por Cockcroft-Gault (integrable con target dosing)
- Ajuste de CL proporcional a CLCr del paciente (explícito y auditable)
- Bayes-MAP básico honesto para 1C: parámetros posteriores + predicciones + sugerencia de ajuste
- Units Gate extendido para validar observaciones y priors v2

**Lo que v2 NO incluye todavía:**
- MCMC (sin Stan / PyMC)
- PK multicompartimental
- Modelos poblacionales específicos por fármaco
- Interacciones farmacológicas
- Intervalos de credibilidad bayesianos completos (`ci = null`)
- Conexión a laboratorio real ni aprendizaje automático

**Acción canónica:** `cockcroft_gault` emite `observe` (solo calcula CLCr). `target_dosing_renal` y `tdm_bayes_map` emiten `review_dosing` — nunca `start_treatment`. Todos los cálculos PK/TDM son orientativos y requieren confirmación con niveles séricos reales y criterio clínico.

**Ejemplos nuevos v2:**
```bash
python run_examples.py
# Incluye ahora:
#   PK_TDM v2 — Cockcroft-Gault
#   PK_TDM v2 — Target Dosing con ajuste renal automático
#   PK_TDM v2 — Bayes-MAP con 1 concentración observada
#   PK_TDM v2 — Bayes-MAP con 3 concentraciones observadas
```

### Sepsis_Protocol_Engine v1 — Detalle

Motor computable de apoyo para estratificación de sepsis basado en criterios Sepsis-3 (Singer 2016, JAMA) adaptados para computabilidad parcial.

**Inputs obligatorios:** `suspected_infection` (bool), `rr` (rpm), `sbp` (mmHg), `mental_status_altered` (bool), `map_mmHg`, `lactate_mmol_L`, `vasopressor` (bool).

**Inputs opcionales:** `urine_output_ml_kg_h`, `creatinine_mg_dL`, `bilirubin_mg_dL`, `platelets_k_uL`, `pao2_fio2`, `mechanical_ventilation`.

| Componente | Criterio |
|------------|----------|
| qSOFA | FR ≥ 22 + PAS ≤ 100 + alteración mental (0–3 puntos; ≥ 2 = positivo) |
| SOFA renal | Creatinina sérica (0–4 pts) — solo si disponible |
| SOFA hepático | Bilirrubina total (0–4 pts) — solo si disponible |
| SOFA coagulación | Plaquetas (0–4 pts) — solo si disponible |
| SOFA respiratorio | PaO2/FiO2 (0–4 pts, con/sin VM) — solo si disponible |
| Lactato | Clasificación: normal / limítrofe / elevado / marcadamente elevado |
| MAP | < 65 mmHg: criterio hemodinámico de choque |
| Hipoperfusión global | Lactato elevado + MAP bajo o vasopresor |

**Clases de severidad:**
- `low_suspicion`: sin sospecha infecciosa o sin señales de disfunción
- `sepsis_probable`: sospecha infecciosa + qSOFA ≥ 2 o SOFA parcial ≥ 2 o lactato ≥ 2.0 mmol/L
- `septic_shock_probable`: sospecha infecciosa + lactato ≥ 2.0 mmol/L + MAP < 65 mmHg y/o vasopresor

**Acción canónica:**
- `observe`: sospecha baja sin señales de disfunción
- `obtain_test`: sepsis probable con datos insuficientes para confirmar
- `start_treatment`: output apoya iniciar manejo clínico inmediato (bundle de alto nivel). **No es una orden autónoma.**

**Tiempo de revaloración:** 15 min (choque), 30 min (sepsis), 60 min (baja sospecha).

**Lo que Sepsis_Protocol_Engine v1 NO incluye todavía:**
- Antibióticos específicos ni dosis
- EHR real ni antibiótico por germen
- SOFA cardiovascular formal ni GCS como score numérico
- Respuesta a fluidos ni evaluación hemodinámica invasiva
- Predicción de mortalidad
- Ventilación mecánica avanzada (solo flag)
- Conexión a APIs hospitalarias

### Lo que hace el MVP

- Recibe un payload JSON clínico estructurado
- Valida schema y restricciones de dominio antes de ejecutar cualquier módulo
- **Bayes SPRT**: actualización secuencial con parada temprana real — en cuanto `p_k ≥ θ_T` o `p_k ≤ θ_A` el loop para; los tests restantes se registran en `tests_skipped` y no se procesan
- Ejecuta interpretación ácido-base o DCA según el módulo solicitado
- **Auditoría dual**: cada registro JSONL incluye dos hashes SHA-256 independientes:
  - `sha256_input`: hash de `{patient_id, module, inputs, version}` **sin timestamp** — determinista; mismo payload → mismo hash; permite detectar duplicados exactos y verificar reproducibilidad
  - `sha256_event`: hash del evento completo incluyendo `timestamp` y `request_id` — único por ejecución; garantiza integridad del registro auditado
- Devuelve salida homogénea con: `result`, `action`, `p`, `U`, `NB`, `units_ok`, `explain`, `ci`, `request_id`

---

## Glosario canónico — Terminología SMNC-5+

### Arquitectura del sistema

**Hipócrates / SMNC-5+**
Motor de cálculo clínico determinista basado en el Sistema Médico Núcleo Computable versión 5+. El nombre "SMNC-5+" designa la especificación formal que define el schema de entrada, el contrato de salida homogénea, las acciones canónicas y los requisitos de auditoría. Hipócrates es la implementación de referencia de esa especificación.

**Motor determinista**
Un sistema donde el mismo payload de entrada produce siempre el mismo resultado clínico y el mismo `sha256_input`, sin componente estocástico ni generativo. Esto lo distingue de los sistemas de IA generativa: no hay aleatoriedad, no hay inferencia probabilística implícita, no hay "alucinaciones". Los campos de trazabilidad por ejecución (`request_id`, timestamp, `sha256_event`) sí varían por diseño — son únicos por corrida, no por payload — pero el cálculo clínico subyacente es siempre reproducible dado el mismo input.

**Tipado / salida homogénea**
Todos los módulos devuelven exactamente el mismo formato de respuesta (`ClinicalOutput`), con los mismos campos en las mismas posiciones, independientemente del módulo o modo. Los campos específicos de cada cálculo se concentran en `result`; los campos de alto nivel (`action`, `p`, `NB`, `units_ok`, `explain`, `ci`, `request_id`) son comunes y consistentes entre módulos.

**Orquestador (`Hipocrates_Orchestrator`)**
Componente que ejecuta el pipeline completo: valida el schema del payload → ejecuta el Units Gate → despacha al módulo correspondiente → registra en auditoría → devuelve el output. Es el único punto de entrada al sistema. La consola visual llama exclusivamente al orquestador; no reimplementa ninguna lógica clínica.

**Schema / `Clinical_IO_Schema`**
Especificación formal de la estructura del payload de entrada. Define qué campos son obligatorios, qué tipos son aceptables y qué módulos son válidos. La validación de schema ocurre antes que la validación de dominio: un payload malformado se rechaza antes de llegar al Units Gate.

**Units Gate / `Units_Validity_Gate`**
Componente de validación de dominio que se ejecuta antes de cada módulo clínico. Verifica que los valores numéricos de los inputs estén dentro de rangos físicamente y clínicamente aceptables: probabilidades en [0,1], parámetros farmacocinéticos positivos, ventanas terapéuticas no invertidas, etc. Si cualquier violación de dominio se detecta, la solicitud se rechaza con `action: blocked` antes de que se ejecute ningún cálculo. La validación de schema y la validación de dominio son capas independientes y secuenciales.

**`units_ok`**
Campo booleano en el output que indica si los inputs superaron la validación del Units Gate. `true` significa que todos los inputs estaban dentro del dominio aceptable y el módulo clínico fue ejecutado. `false` indica que la solicitud fue rechazada. No evalúa la calidad clínica de los inputs — solo su validez matemática y de dominio.

**`request_id`**
Identificador UUID v4 generado de forma única para cada ejecución del sistema. No expresa gravedad, calidad ni importancia del resultado. Sirve exclusivamente como enlace entre el output visible al usuario y el registro persistente en el log de auditoría. Permite localizar un resultado específico, verificar que el output mostrado corresponde al registro auditado, y reproducir la solicitud con exactamente los mismos parámetros.

**`sha256_input`**
Hash SHA-256 calculado sobre `{patient_id, module, inputs, version}` sin timestamp ni request_id. Es determinista: el mismo payload de entrada produce siempre el mismo hash. Permite detectar solicitudes duplicadas, verificar que los inputs registrados son idénticos a los que generaron el output, y garantizar que el cálculo es reproducible externamente.

**`sha256_event`**
Hash SHA-256 calculado sobre el evento de auditoría completo, incluyendo timestamp, request_id y output. Es único por ejecución, incluso si los inputs son idénticos. Garantiza la integridad del registro tal como fue emitido: cualquier modificación posterior del archivo JSONL alteraría este hash.

**`explain`**
Campo de texto en el output que contiene el razonamiento textual del sistema para el resultado producido. No es una narrativa clínica autónoma — es la descripción formal de qué calculó el módulo y qué condiciones determinaron la acción emitida. Debe leerse como complemento del output estructurado, no como sustituto de la interpretación clínica.

**`ci` (intervalo de confianza)**
Campo reservado en el output, actualmente `null` en v1.0. Previsto para versiones futuras con cuantificación de incertidumbre estadística. La ausencia de `ci` no implica certeza — implica que esta versión no implementa cuantificación formal de incertidumbre.

**`U` (utilidad clínica esperada)**
Campo reservado en el output, actualmente `null` en v1.0. Previsto para módulos de teoría de la utilidad que ponderan los outcomes clínicos con sus probabilidades. No confundir con el beneficio neto `NB` de DCA.

### Acciones canónicas

Las acciones son clasificaciones formales del resultado computacional. No son órdenes clínicas autónomas — son orientaciones de alto nivel que requieren interpretación por el clínico en el contexto del paciente.

| Acción | Condición de emisión | Módulo |
|--------|---------------------|--------|
| `start_treatment` | p posterior ≥ θ_T | Bayes SPRT |
| `discard_diagnosis` | p posterior ≤ θ_A | Bayes SPRT |
| `obtain_test` | p no cruzó ningún umbral tras todos los tests | Bayes SPRT |
| `observe` | Resultado calculado sin indicación de acción inmediata | ABG, PK simulación |
| `review_dosing` | Recomendación de dosificación PK orientativa | PK/TDM (todos los modos) |
| `use_model` | NB(modelo) > NB(tratar-todos) y NB(no-tratar) en θ | DCA |
| `do_not_use_model` | NB(modelo) ≤ alternativas en θ | DCA |
| `restrict_to_threshold_range` | NB(modelo) > alternativas solo en subconjunto del rango | DCA |
| `blocked` | Violación de dominio detectada por Units Gate | Todos |

### Módulo Bayes SPRT

**p₀ (probabilidad pretest)**
Estimación de la probabilidad del diagnóstico de interés antes de aplicar cualquier test. Corresponde a la prevalencia ajustada al contexto clínico específico del paciente (edad, sexo, presentación, epidemiología local). No es la prevalencia poblacional cruda — es la probabilidad *a priori* que el clínico asigna al diagnóstico en ese paciente concreto.

**p posterior**
Probabilidad del diagnóstico tras incorporar secuencialmente los resultados de los tests aplicados. Se actualiza mediante la regla de Bayes en forma de odds: `odds_k = odds_{k-1} × LR_k`. La p posterior es el resultado central del módulo Bayes.

**LR (razón de verosimilitud)**
Cociente entre la probabilidad del resultado del test dado que el diagnóstico es verdadero y la probabilidad del mismo resultado dado que el diagnóstico es falso. LR > 1 aumenta la probabilidad posterior; LR < 1 la disminuye. Para un resultado negativo se aplica el inverso: 1/LR.

**θ_T (umbral de tratamiento)**
Valor de probabilidad posterior tal que, si p ≥ θ_T, la evidencia acumulada se considera suficiente para decidir tratar. El sistema emite `start_treatment`. Es una decisión de política clínica, no un umbral objetivo del sistema.

**θ_A (umbral de descarte)**
Valor de probabilidad posterior tal que, si p ≤ θ_A, la evidencia acumulada se considera suficiente para descartar el diagnóstico. El sistema emite `discard_diagnosis`.

**Parada temprana SPRT**
Mecanismo del procedimiento secuencial de Wald: el loop de actualización bayesiana se detiene en cuanto p cruza θ_T o θ_A. Los tests restantes no son procesados — esto no es un error ni un fallo del sistema. Es la decisión formal del procedimiento: con la información acumulada ya es posible tomar una decisión sin tests adicionales. Los tests no procesados quedan registrados en `tests_skipped`.

**`obtain_test`**
Acción emitida cuando el SPRT agota todos los tests disponibles sin que p cruce ningún umbral. Indica que la evidencia disponible es insuficiente para decidir tratar o descartar. No es un fallo del sistema — es la respuesta correcta cuando los datos disponibles no permiten una conclusión bayesiana.

### Módulo Ácido-Base (ABG H-H / Stewart)

**Trastorno primario**
Identificación del desequilibrio ácido-base principal: acidosis o alcalosis, de origen respiratorio o metabólico. Se determina por la dirección del pH y el componente causal predominante (PaCO₂ para trastornos respiratorios, HCO₃⁻ para metabólicos).

**Compensación esperada**
Respuesta fisiológica del componente complementario al trastorno primario. El sistema verifica si la PaCO₂ o el HCO₃⁻ del paciente corresponde al rango de compensación esperado según las fórmulas estándar. Una compensación fuera del rango esperado sugiere un trastorno mixto.

**Diagnóstico gasométrico formal (etiqueta formal)**
Denominación canónica del trastorno, incorporando el trastorno primario, su naturaleza (aguda/crónica cuando aplica) y el estado de compensación. Ejemplo: "acidosis metabólica con compensación respiratoria adecuada".

**AG (brecha aniónica)**
AG = Na⁺ − (Cl⁻ + HCO₃⁻). Estima la concentración de aniones no medidos en plasma. Valor normal aproximado: 12 ± 2 mEq/L. AG elevado indica presencia de aniones ácidos no medidos (lactato, cetonas, tóxicos, uremia).

**AG corregido por albúmina**
Corrección del AG para compensar el efecto de la hipoalbuminemia: AG_corr = AG + 2.5 × (4.0 − albúmina). La hipoalbuminemia reduce el AG observado, enmascarando brechas aniónicas verdaderamente elevadas. Sin esta corrección, una acidosis con AG elevado puede no detectarse en pacientes hipoalbuminémicos.

**Delta-delta (Δ/Δ)**
Δ/Δ = (AG − 12) / (24 − HCO₃⁻). Evalúa si en presencia de AG elevado existe también un trastorno metabólico superpuesto. Δ/Δ < 1 sugiere acidosis metabólica sin AG concomitante; Δ/Δ > 2 sugiere alcalosis metabólica concomitante.

**Winter (PaCO₂ esperada)**
Fórmula de compensación respiratoria en acidosis metabólica: PaCO₂ esperada = 1.5 × HCO₃⁻ + 8 ± 2 mmHg. Si la PaCO₂ real es mayor que el límite superior → acidosis respiratoria superpuesta. Si es menor → alcalosis respiratoria superpuesta.

**SIDa (Diferencia iónica fuerte aparente)**
En el marco de Stewart: SIDa = Na⁺ + K⁺ + Ca²⁺ + Mg²⁺ − Cl⁻ − Lactato. Representa la diferencia entre cationes y aniones fuertes (completamente disociados). Valor normal ≈ 40–42 mEq/L. Esta implementación es una *aproximación* al modelo completo de Stewart.

**Atot (buffer no volátil total)**
Atot = 2.43 × albúmina + fosfato/5.5. Concentración total de ácidos débiles no volátiles, principalmente albúmina y fosfato. Junto con SIDa, determina el estado ácido-base en el marco fisicoquímico.

**Consistencia del pH**
El sistema recalcula el pH teórico por Henderson-Hasselbalch a partir de PaCO₂ y HCO₃⁻ y lo compara con el pH medido. Una discrepancia |Δ| > 0.05 unidades indica inconsistencia entre los valores introducidos: posible error de transcripción, error de laboratorio, o valores correspondientes a muestras o tiempos distintos.

### Módulo DCA (Decision Curve Analysis)

**Beneficio neto (NB)**
Métrica que pondera los verdaderos positivos menos los falsos positivos ponderados por el umbral θ: NB = TPR × prevalencia − FPR × (1−prevalencia) × θ/(1−θ). Refleja la utilidad clínica neta del modelo en ese umbral, expresada en unidades de verdaderos positivos por paciente.

**θ (umbral de decisión clínica)**
Probabilidad mínima del evento que justifica la intervención. Codifica implícitamente el balance coste/beneficio entre intervenir (riesgo de falso positivo) y no intervenir (riesgo de falso negativo). Un θ bajo indica alta aversión al riesgo de pasar por alto el diagnóstico; un θ alto indica mayor tolerancia.

**Tratar-todos (treat-all)**
Estrategia de referencia que interviene sobre todos los pacientes sin discriminación. NB(tratar-todos) = prevalencia − (1−prevalencia) × θ/(1−θ). Es la estrategia óptima cuando θ es muy bajo (no importa tratar a los que no lo necesitan).

**No-tratar (treat-none)**
Estrategia de referencia que no interviene sobre ningún paciente. NB(no-tratar) = 0 por definición. Es la estrategia óptima cuando los riesgos de la intervención superan cualquier beneficio posible.

**Rango útil del modelo**
Conjunto de valores de θ en los que el NB del modelo supera al NB de ambas estrategias de referencia. El modelo solo tiene valor clínico añadido dentro de este rango. Fuera de él, una estrategia más simple (tratar-todos o no-tratar) produce igual o mayor beneficio neto.

**`use_model`**
El modelo genera más beneficio neto que las estrategias alternativas en el θ de referencia evaluado. No significa que el modelo sea perfecto — significa que, para ese umbral de decisión específico, usarlo produce más beneficio ajustado por riesgo que no usarlo.

**`restrict_to_threshold_range`**
El modelo es clínicamente útil solo en un subconjunto del rango de θ evaluado. Fuera de ese subconjunto, una estrategia más simple produce igual o mayor NB.

### Módulo PK/TDM Core

**Css (concentración en estado estacionario)**
Concentración plasmática que se alcanza cuando la tasa de entrada del fármaco iguala la tasa de eliminación. Css = R₀/CL para infusión continua. Para dosis repetidas, se alcanza aproximadamente tras 4-5 semividas.

**Cmax_ss / Cmin_ss**
Concentración máxima y mínima en estado estacionario para regímenes de dosis repetidas. Cmax_ss = (D/Vd) / (1−exp(−k·τ)); Cmin_ss = Cmax_ss × exp(−k·τ).

**Target dosing — LD / MD**
Cálculo inverso: dada una Css objetivo, la dosis de carga (LD = Css·Vd/F) satura el volumen de distribución inmediatamente; la dosis de mantenimiento (MD = Css·CL·τ/F) repone lo eliminado en cada intervalo τ. Son estimaciones de primer orden con parámetros poblacionales — requieren verificación con niveles séricos.

**Ventana terapéutica (simulada)**
Rango de concentraciones plasmáticas [C_min_terapéutica, C_max_terapéutica] introducido por el usuario. El calificativo "simulada" indica que la comparación se realiza contra este rango predefinido en el formulario, no contra niveles séricos medidos en el paciente. La determinación de la ventana terapéutica clínicamente relevante es responsabilidad del clínico.

**`review_dosing`**
Acción emitida por todos los modos de PK/TDM Core v2.0. Formaliza que el resultado es un cálculo orientativo: el sistema no emite `start_treatment` para dosificación porque opera sin contexto clínico completo. Incluso los modos bayesianos (Bayes-MAP) producen estimaciones que requieren verificación con niveles séricos adicionales y revisión clínica antes de cualquier aplicación.

**Convergencia (fenitoína MM)**
El algoritmo de Michaelis-Menten itera sobre dosis candidatas hasta encontrar una que produzca una Css estimada dentro de la ventana terapéutica objetivo. "Convergencia" indica que se encontró una dosis candidata dentro del número máximo de ensayos. "Sin convergencia" indica que el algoritmo agotó los ensayos sin encontrar una dosis que cumpla el criterio — no es un error del sistema, es un reporte honesto de que los parámetros introducidos no permiten alcanzar la ventana en esas condiciones.

**Ajuste renal proporcional**
new_dose = std_dose × (CLCr_paciente / CLCr_referencia). Ajuste de primer orden que asume linealidad entre aclaramiento renal y eliminación del fármaco. Solo válido para fármacos con eliminación predominantemente renal y cinética lineal.

---

## Qué NO incluye todavía

- `Glucose_MPC_Controller` — control glucémico por MPC
- `ERV_API_Connector` / `ERV_Review_Queue` — sistema ERV
- `LUM_Diagnostic_Engine` — LUM/Psicología
- `Psychopathology_M1M2M3_Engine`
- UI de producción / frontend público / despliegue en servidor (sí existe una consola visual local de demo en `app/streamlit_app.py`, pero no hay UI pública ni despliegue)
- APIs externas, base de datos, Docker

---

## Estructura del proyecto

```
hipocrates/
  src/hipocrates/
    core/
      io_schema.py       # Clinical_IO_Schema
      units_gate.py      # Units_Validity_Gate
      audit.py           # Audit_Log_Provenance
      orchestrator.py    # Hipocrates_Orchestrator
    modules/
      bayes_sprt.py      # Bayes_SPRT_Engine
      abg_hh_stewart.py  # ABG_HH_Stewart_Engine
      dca.py             # DCA_Utility_Module
      pk_tdm.py          # PK_TDM_Core v2.0
      sepsis_protocol.py # Sepsis_Protocol_Engine v1
    utils/
      types.py           # ClinicalInput / ClinicalOutput / Action
      math_utils.py      # odds, prob, log seguro
      validation.py      # helpers de dominio
  tests/                 # 338 tests pytest
  examples/              # 14 JSON de ejemplo; run_examples ejecuta 13
  outputs/               # audit_log.jsonl (generado en ejecución)
  app/
    streamlit_app.py     # Consola visual local (demo)
    ui_helpers.py        # Helpers de presentación
  run_examples.py
  requirements.txt
  pyproject.toml
```

---

## Cómo instalar

```bash
cd hipocrates
pip install -e .
pip install -r requirements.txt
```

---

## Consola visual local (Streamlit)

> **Demo local únicamente. No despliegue público. No uso clínico autónomo.**

La consola conecta directamente al núcleo Hipócrates: no reimplementa lógica clínica, solo recoge inputs, llama al orquestador y muestra resultados.

**Módulos cubiertos:** Bayes SPRT · Ácido–Base H–H/Stewart · DCA · PK/TDM Core · Sepsis

```bash
cd hipocrates
streamlit run app/streamlit_app.py
```

Abre automáticamente en `http://localhost:8501`. Paneles disponibles:

- 🏠 **Inicio** — descripción del sistema, arquitectura, estructura de respuesta, glosario de acciones
- 🎲 **Bayes SPRT** — formulario interactivo con traza secuencial de actualización bayesiana
- 🫁 **Ácido–Base** — gasometría completa con AG, AG corregido, Winter, delta-delta, SIDa, Atot
- 📊 **DCA** — curva de beneficio neto interactiva con gráfico NB(θ)
- 💊 **PK/TDM** — 10 modos con campos dinámicos según modo seleccionado
- 🦠 **Sepsis** — clasificación qSOFA/SOFA con bundle de acciones y tiempo de revaloración
- 📋 **Trazabilidad** — últimos registros JSONL con SHA-256 dual y UUID, explicación de campos

---

## Cómo ejecutar los ejemplos

```bash
python run_examples.py
```

Ejecuta 13 casos: Bayes SPRT, ácido-base, DCA, 6 modos PK/TDM (IV bolus, target dosing, fenitoína MM, Cockcroft-Gault, target dosing con ajuste renal, Bayes-MAP ×2) y 3 escenarios de sepsis (sospecha baja, sepsis probable, choque séptico). Muestra la salida completa por consola. El log de auditoría se escribe en `outputs/audit_log.jsonl`.

---

## Cómo correr los tests

```bash
python -m pytest tests/ -v
```

Resultado esperado: **338 passed**.

Para ver solo el resumen:

```bash
python -m pytest tests/ -q
```

---

## Formato del payload de entrada

```json
{
  "patient_id": "PAC-001",
  "module": "bayes_sprt",
  "inputs": { "p0": 0.25, "tests": [...], "theta_T": 0.8, "theta_A": 0.05 },
  "constraints": {},
  "version": "SMNC-5+_v1.0"
}
```

Módulos válidos en este MVP: `bayes_sprt`, `abg_hh_stewart`, `dca`, `pk_tdm`, `sepsis_protocol`.

Para `pk_tdm`, el campo `inputs.mode` selecciona el cálculo:

```json
{
  "patient_id": "PAC-001",
  "module": "pk_tdm",
  "inputs": {
    "mode": "iv_bolus",
    "dose_mg": 500,
    "vd_L": 30,
    "cl_L_h": 3.5,
    "time_h": 4
  },
  "constraints": {},
  "version": "SMNC-5+_v1.0"
}
```

## Estructura de respuesta del sistema

Todos los módulos devuelven exactamente este formato (`ClinicalOutput`). Los campos de alto nivel son homogéneos entre módulos; `result` contiene los datos específicos del cálculo.

```json
{
  "result":     { "...datos específicos del módulo..." },
  "action":     "start_treatment | discard_diagnosis | obtain_test | observe | review_dosing | use_model | ...",
  "p":          0.889,
  "U":          null,
  "NB":         { "theta": 0.15, "value": 0.138 },
  "units_ok":   true,
  "explain":    "razonamiento textual del sistema para este output",
  "ci":         null,
  "request_id": "uuid-v4"
}
```

---

## Criterio de uso y limitaciones

Este sistema es un **prototipo de investigación**. En ningún caso debe usarse como único criterio para decisiones clínicas reales. Los cálculos implementan fórmulas estándar de la literatura médica, pero:

- No han sido validados clínicamente en poblaciones reales
- No reemplazan la evaluación médica directa
- Los outputs deben ser interpretados por personal clínico competente
- El sistema no conoce el contexto clínico completo del paciente
- Los parámetros farmacocinéticos son poblacionales o ingresados manualmente: sin individualización

**Uso aceptable:** investigación, educación, simulación, prototipado de sistemas de apoyo a la decisión.

**Uso inaceptable:** decisiones clínicas autónomas, prescripción, diagnóstico definitivo sin supervisión médica.

---

## Licencia

Este proyecto se publica bajo la licencia MIT. Ver el archivo `LICENSE`.

---

## Cómo citar

Este proyecto no tiene aún un identificador persistente (DOI) ni publicación formal. Si se usa este código como referencia en un trabajo de investigación, se sugiere citar el repositorio directamente:

```
Jules Pintor. Hipócrates — Motor de Apoyo Clínico Computable (SMNC-5+). 
Prototipo de investigación. Versión 0.5.0. Abril 2026.
https://github.com/julespintor-tech/hipocrates
```

Un archivo `CITATION.cff` está incluido en este repositorio con los metadatos formales sugeridos.

---

## Estado del proyecto

- Versión: `0.5.0`
- Estado: prototipo público de investigación — primera snapshot pública
- Tests: 338 passed (verificados en Python 3.10 y 3.13)
- Módulos clínicos: 5 (Bayes SPRT, ABG H-H/Stewart, DCA, PK/TDM Core v2, Sepsis v1)
- Validación clínica: **ninguna** — prototipo computacional únicamente
- Despliegue en producción: **no existe**
docs: update README license and citation link

