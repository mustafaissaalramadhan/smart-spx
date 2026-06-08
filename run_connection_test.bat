@echo off
chcp 65001 > nul
cd /d "%~dp0"
python test_ibkr_connections.py
pause
