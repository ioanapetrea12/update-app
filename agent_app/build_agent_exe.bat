@echo off
setlocal
cd /d %~dp0

echo === Build RSR Agent ===
cd ..

cd agent_app

echo === 1. Actualizez pip la ultima versiune ===
python -m pip install --upgrade pip

echo === 2. Instalez dependintele din requirements.txt ===
pip install -r requirements.txt

echo === 3. Curat builduri vechi ===
rd /s /q build
rd /s /q dist

echo === 4. Construiesc executabilul cu PyInstaller ===
pyinstaller --clean agent.spec

copy scripts\register_agent_startup.bat dist\agent_update_RSR\ >nul
copy scripts\unregister_agent_startup.bat dist\agent_update_RSR\ >nul

echo === 6. Creez arhiva .zip pentru distributie ===
cd dist\agent_update_RSR
set ZIP_NAME=..\RSR_Agent_Distributie.zip
powershell -Command "Compress-Archive -Path * -DestinationPath '%ZIP_NAME%' -Force"

cd ../..
echo === Gata! Arhiva este: agent_app\dist\RSR_Agent_Distributie.zip ===
pause