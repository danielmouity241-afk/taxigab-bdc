@echo off
title TAXI GAB+ - Bons de Commande
cd /d "C:\Users\hp\.gemini\antigravity\scratch\taxigab-bdc"

set "PY=C:\Users\hp\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

echo ======================================================
echo    TAXI GAB+ - Demarrage du systeme BDC...
echo ======================================================
echo   Acces local: http://localhost:5000
echo   Identifiant: dt
echo   Mot de passe: DT@2026!
echo ======================================================
echo   Ne fermez pas cette fenetre pendant l'utilisation.
echo ======================================================

start http://localhost:5000

"%PY%" app.py

pause
