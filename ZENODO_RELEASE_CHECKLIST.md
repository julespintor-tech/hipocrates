# Checklist de depósito en Zenodo — Hipócrates v0.5.0

Checklist paso a paso para subir Hipócrates a Zenodo de forma limpia y archivísticamente honesta.

---

## ANTES DE SUBIR — Verificación local

- [ ] Verificar que el release `v0.5.0` está publicado en GitHub:
  https://github.com/julespintor-tech/hipocrates/releases/tag/v0.5.0

- [ ] Verificar que el tag `v0.5.0` apunta al commit correcto:
  Commit esperado: `97acb51`

- [ ] Confirmar que el local está en sync con origin/main (0 commits de diferencia).

- [ ] Verificar que `README.md`, `CITATION.cff`, `CHANGELOG.md` y `RELEASE_NOTES_v0.5.0.md`
  están presentes y sin errores obvios.

- [ ] Confirmar que `outputs/audit_log.jsonl` NO se incluirá en el depósito.

- [ ] Confirmar que `diagnostico_resultado.txt` NO se incluirá en el depósito
  (contiene rutas locales del sistema).

- [ ] Confirmar que `COMANDOS_PUBLICACION_FINAL.md` NO se incluirá
  (es un archivo de trabajo interno, no rastreado en git).

---

## OPCIÓN A — Depósito vía integración GitHub (recomendada)

Esta opción usa el `.zenodo.json` del repositorio para pre-poblar la metadata.

1. Ir a https://zenodo.org y autenticarse con la cuenta del autor.

2. En Zenodo → GitHub (menú superior o https://zenodo.org/account/settings/github):
   - Buscar el repositorio `julespintor-tech/hipocrates`.
   - Activar el toggle para habilitar la integración.
   - Si el release `v0.5.0` ya está publicado y la integración estaba activa antes del release,
     Zenodo puede haberlo detectado automáticamente.
   - Si la integración se activa después del release, ir a "Releases" y hacer clic en
     "Sync" o crear un nuevo release desde GitHub para disparar la indexación.

3. Una vez Zenodo cree el borrador automático:
   - Revisar todos los campos (pre-poblados desde `.zenodo.json`).
   - Completar los campos PENDIENTES según corresponda (ver tabla en ZENODO_METADATA.md).
   - Verificar que la descripción no contiene claims clínicos falsos.
   - Verificar que la advertencia de uso está visible.

4. Publicar. Zenodo asignará un DOI.

5. Actualizar `CITATION.cff` con el DOI asignado.

---

## OPCIÓN B — Depósito manual con zip limpio

Usar si la integración GitHub no está disponible o se prefiere subir manualmente.

### Paso 1 — Obtener el zip del release de GitHub

Descargar directamente desde:
```
https://github.com/julespintor-tech/hipocrates/archive/refs/tags/v0.5.0.zip
```

El zip de GitHub incluye exactamente lo que está en el repositorio en ese tag.
No incluye `__pycache__`, `.git`, `.pytest_cache` (están en `.gitignore`).

> ALTERNATIVA: clonar el repo, hacer checkout del tag y crear el zip manualmente
> (ver Paso 1b más abajo si se necesita limpiar más).

### Paso 1b — SOLO si se necesita zip limpio adicional (opcional)

Si se quiere excluir `diagnostico_resultado.txt` o `COMANDOS_PUBLICACION_FINAL.md`
(que están fuera del índice git), usar el zip de GitHub directamente — ya son archivos
no rastreados y no estarán en el zip del release de GitHub.

### Paso 2 — Verificar el zip

Antes de subir, abrir el zip y confirmar que NO contiene:
- [ ] `__pycache__/` en ningún subdirectorio
- [ ] `.pytest_cache/`
- [ ] `outputs/audit_log.jsonl`
- [ ] `diagnostico_resultado.txt`
- [ ] `COMANDOS_PUBLICACION_FINAL.md`
- [ ] `src/hipocrates.egg-info/`
- [ ] `pytest-cache-files-*`
- [ ] Archivos `.streamlit/credentials.toml` o `.streamlit/secrets.toml`

Confirmar que SÍ contiene:
- [ ] `README.md`
- [ ] `LICENSE`
- [ ] `CITATION.cff`
- [ ] `CHANGELOG.md`
- [ ] `RELEASE_NOTES_v0.5.0.md`
- [ ] `.zenodo.json`
- [ ] `ZENODO_METADATA.md`
- [ ] `ZENODO_RELEASE_CHECKLIST.md`
- [ ] `pyproject.toml`
- [ ] `requirements.txt`
- [ ] `src/` (código fuente)
- [ ] `tests/` (suite de tests)
- [ ] `examples/` (14 ejemplos JSON)
- [ ] `app/` (consola Streamlit)

### Paso 3 — Subir a Zenodo

1. Ir a https://zenodo.org/uploads/new
2. Subir el zip del release.
3. Rellenar el formulario con los campos de ZENODO_METADATA.md.
4. Añadir los identificadores relacionados (GitHub release + repo).
5. Verificar la advertencia de uso en el campo "Notes".
6. Seleccionar "Open Access" y licencia MIT.
7. Publicar.

---

## DESPUÉS DE PUBLICAR

- [ ] Copiar el DOI asignado por Zenodo (formato: `10.5281/zenodo.XXXXXXX`)

- [ ] Actualizar `CITATION.cff`:
  Añadir o reemplazar el campo `doi`:
  ```yaml
  doi: "10.5281/zenodo.XXXXXXX"
  ```

- [ ] (Opcional) Actualizar `README.md` con el badge de Zenodo:
  ```markdown
  [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
  ```

- [ ] Hacer commit y push de los cambios a GitHub.

- [ ] Verificar que el registro de Zenodo es accesible públicamente.

---

## Qué NO afirmar en Zenodo

- NO afirmar que el sistema ha sido validado clínicamente.
- NO afirmar que es apto para uso en pacientes reales.
- NO afirmar que los outputs son diagnósticos o recomendaciones terapéuticas.
- NO inflar el número de tests ni las capacidades del sistema.
- NO incluir DOI, ORCID, funding ni afiliaciones no verificadas.
- NO afirmar que es un "sistema de IA" (es un motor determinista basado en reglas y fórmulas).

---

## Estado verificado al generar este archivo (2026-04-08)

| Elemento | Estado |
|----------|--------|
| Release GitHub v0.5.0 | Publicado ✓ |
| Tag v0.5.0 (commit 97acb51) | Presente ✓ |
| README.md | Presente, con advertencia de uso ✓ |
| LICENSE (MIT) | Presente ✓ |
| CITATION.cff | Presente, sin DOI (PENDIENTE) ✓ |
| CHANGELOG.md | Presente ✓ |
| RELEASE_NOTES_v0.5.0.md | Presente ✓ |
| .zenodo.json | Creado ✓ |
| ZENODO_METADATA.md | Creado ✓ |
| 338 tests pytest | Verificados en esta sesión ✓ |
| outputs/audit_log.jsonl | Presente localmente — EXCLUIR del depósito ✓ |
| DOI Zenodo | PENDIENTE |
| ORCID autor | PENDIENTE |
| Afiliación | PENDIENTE |
| Funding | PENDIENTE |
