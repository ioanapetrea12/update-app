@echo off
set EXE_PATH=%~dp0agent_update_RSR.exe

echo Creare task în Task Scheduler...
schtasks /create ^
  /tn "RSR_Agent" ^
  /tr "C:\RSR\Agent\agent_update_RSR.exe" ^
  /sc onstart ^
  /rl highest ^
  /ru SYSTEM ^
  /f



echo Taskul RSR_Agent a fost creat pentru a porni la boot.
pause