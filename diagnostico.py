"""
diagnostico.py - Ejecuta con: python diagnostico.py
Escribe resultado en diagnostico_resultado.txt
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "diagnostico_resultado.txt"

lines = []

def log(msg=""):
    print(msg)
    lines.append(msg)

log("=" * 60)
log("DIAGNOSTICO HIPOCRATES")
log("=" * 60)
log()

# 1. Python
log(f"[1] Python ejecutable : {sys.executable}")
log(f"    Version            : {sys.version}")
log()

# 2. CWD y rutas criticas
log(f"[2] Directorio actual  : {Path.cwd()}")
log(f"    Raiz proyecto      : {ROOT}")
log(f"    app/streamlit_app  : {(ROOT / 'app' / 'streamlit_app.py').exists()}")
log(f"    app/ui_helpers.py  : {(ROOT / 'app' / 'ui_helpers.py').exists()}")
log(f"    src/hipocrates     : {(ROOT / 'src' / 'hipocrates').exists()}")
log(f"    requirements.txt   : {(ROOT / 'requirements.txt').exists()}")
log()

# 3. Streamlit instalado?
log("[3] Probando: python -m streamlit --version")
r = subprocess.run(
    [sys.executable, "-m", "streamlit", "--version"],
    capture_output=True, text=True
)
log(f"    stdout: {r.stdout.strip()}")
log(f"    stderr: {r.stderr.strip()}")
log(f"    returncode: {r.returncode}")
log()

# 4. Import del nucleo
log("[4] Probando import de hipocrates:")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
try:
    from hipocrates.core.orchestrator import run
    log("    hipocrates.core.orchestrator -> OK")
except Exception as e:
    log(f"    ERROR: {e}")
try:
    import ui_helpers
    log("    ui_helpers -> OK")
except Exception as e:
    log(f"    ERROR ui_helpers: {e}")
log()

# 5. Import completo del app (como lo haria streamlit)
log("[5] Probando import de streamlit_app completo:")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "streamlit_app", ROOT / "app" / "streamlit_app.py"
    )
    # No ejecutamos (st.* crashearia fuera de streamlit), solo cargamos spec
    log(f"    spec cargado: {spec is not None}")
    log("    (ejecucion real requiere entorno Streamlit - esto es solo verificacion de ruta)")
except Exception as e:
    log(f"    ERROR: {e}")
log()

# 6. Puerto 8501 libre?
log("[6] Verificando puerto 8501:")
import socket
try:
    s = socket.socket()
    s.settimeout(1)
    result = s.connect_ex(("localhost", 8501))
    s.close()
    if result == 0:
        log("    Puerto 8501 OCUPADO (algo ya está corriendo ahi, o hay conflicto)")
    else:
        log("    Puerto 8501 LIBRE (listo para Streamlit)")
except Exception as e:
    log(f"    ERROR al verificar puerto: {e}")
log()

# 7. Escribir resultado
log("=" * 60)
log("FIN DEL DIAGNOSTICO")
log("=" * 60)

OUT.write_text("\n".join(lines), encoding="utf-8")
print()
print(f">>> Resultado guardado en: {OUT}")
print(">>> Comparte ese archivo o su contenido para continuar el diagnostico.")
