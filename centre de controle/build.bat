@echo off
REM Compile sensor_panel puis CentreControle en mode "onedir" (exe + dossier _internal a cote).
REM Onedir = aucune extraction temporaire _MEI, ce qui elimine definitivement
REM   - "Failed to start embedded python interpreter"
REM   - "Failed to remove temporary directory _MEI..."
REM et rend le demarrage instantane (pas de ~1s d'extraction).
REM Prerequis : pip install pyinstaller
setlocal
cd /d "%~dp0"

echo [0/3] stoppe les instances en cours (l'exe en cours de lecture serait verrouille) ...
taskkill /f /im sensor_panel.exe >nul 2>&1
taskkill /f /im CentreControle.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo [1/3] compile le panel ...
python -m PyInstaller --noconsole --clean -y --name sensor_panel --contents-directory panel_internal sensor_panel.py
if errorlevel 1 goto err
move /y "dist\sensor_panel\sensor_panel.exe" "sensor_panel.exe" >nul
if exist panel_internal rmdir /s /q panel_internal
move /y "dist\sensor_panel\panel_internal" "panel_internal" >nul
rmdir /s /q dist build 2>nul
del sensor_panel.spec 2>nul

echo [2/3] compile le centre de controle ...
python -m PyInstaller --noconsole --clean -y --name centre_controle --icon "oscilloscope.ico" centre_controle.py
if errorlevel 1 goto err
move /y "dist\centre_controle\centre_controle.exe" "CentreControle.exe" >nul
move /y "dist\centre_controle\_internal" "_internal" >nul
rmdir /s /q dist build 2>nul
del centre_controle.spec 2>nul

echo [3/3] purge les restes _MEI laisses par l'ancien mode onefile ...
for /d %%D in ("%TEMP%\_MEI*") do rmdir /s /q "%%D" >nul 2>&1

echo.
echo OK : CentreControle.exe (+ _internal) et sensor_panel.exe (+ panel_internal)
echo Garde les deux LA OU ILS SONT : l'exe charge son dossier _internal voisin.
pause
exit /b 0
:err
echo ECHEC de compilation
pause
exit /b 1
