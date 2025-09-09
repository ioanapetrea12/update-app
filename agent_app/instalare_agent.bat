@echo off
echo === Oprire agent daca ruleaza ===
taskkill /f /im agent_update_RSR.exe >nul 2>&1

echo === Stergere versiune veche ===
rd /s /q "C:\RSR\Agent\_internal" >nul 2>&1
del /f /q "C:\RSR\Agent\agent_update_RSR.exe" >nul 2>&1

echo === Extragere distributie ===
powershell -Command "Expand-Archive -Path 'C:\RSR\Agent\RSR_Agent_Distributie.zip' -DestinationPath 'C:\RSR\Agent' -Force"

echo === Inregistrare pornire la boot ===
call C:\RSR\Agent\register_agent_startup.bat

echo === Lansare agent ===
start C:\RSR\Agent\agent_update_RSR.exe

echo === Instalare finalizata. ===
pause