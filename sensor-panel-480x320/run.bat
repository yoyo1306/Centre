@echo off
REM Lance le SensorPanel en admin (requis pour la temp CPU Ryzen via LibreHardwareMonitor).
REM Double-clic suffit : le script se re-lance tout seul en admin (prompt UAC a accepter).
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
python probe_temp.py > "%TEMP%\panel_temp_probe.txt" 2>&1
start "" pythonw sensor_panel.py %*
