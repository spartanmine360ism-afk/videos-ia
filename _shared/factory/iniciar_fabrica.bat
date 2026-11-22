@echo off
chcp 65001 >nul
cd /d "C:\Users\aldo_\Desktop\videos-ia"

echo [%date% %time%] Limpiando procesos residuales de render... >> "_shared\factory\arranque_windows.log"
taskkill /F /IM chrome.exe /FI "WINDOWTITLE eq " >nul 2>&1

echo [%date% %time%] Iniciando autopilot_maestro.py... >> "_shared\factory\arranque_windows.log"
python "_shared\factory\autopilot_maestro.py" >> "_shared\factory\arranque_windows.log" 2>&1
echo [%date% %time%] Finalizado con codigo %ERRORLEVEL%. >> "_shared\factory\arranque_windows.log"
