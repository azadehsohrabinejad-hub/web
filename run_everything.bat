@echo off
cd /d "C:\web"
call "C:\web\venv\Scripts\activate.bat" >nul

echo Starting Background Service...
start "" /min "C:\web\venv\Scripts\pythonw.exe" "C:\web\background.py"

echo Starting Web App...
"C:\web\venv\Scripts\waitress-serve.exe" --host=0.0.0.0 --port=5000 --call app:create_app > C:\web\waitress_log.txt 2>&1