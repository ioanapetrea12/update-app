@echo off
REM Activare mediu virtual dacă este cazul
REM call venv\Scripts\activate

echo ==== Instalare dependințe ====
pip install flask waitress pyinstaller

echo ==== Construire agent.exe ====
pyinstaller --clean agent.spec

echo ==== Gata! Găsești fișierul în dist\agent_update_RSR\ ====
pause