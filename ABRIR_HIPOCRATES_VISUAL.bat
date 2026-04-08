@echo off
cd /d "%~dp0"

echo.
echo ==========================================
echo  HIPOCRATES -- Consola visual local
echo ==========================================
echo.
echo  IMPORTANTE: No cierres esta ventana.
echo  La app corre en: http://localhost:8501
echo.

python -c "import pathlib; c=pathlib.Path.home()/'.streamlit'/'credentials.toml'; c.parent.mkdir(parents=True,exist_ok=True); c.write_text('[general]\nemail=\"\"\n',encoding='utf-8') if not c.exists() else None"

cmd /k "python -m streamlit run app/streamlit_app.py"
