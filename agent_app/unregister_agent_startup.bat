@echo off
echo Ștergere task din Task Scheduler...
schtasks /delete /tn "RSR_Agent" /f

echo Taskul RSR_Agent a fost șters.
pause