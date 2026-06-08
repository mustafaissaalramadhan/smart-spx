@echo off
chcp 65001 >nul
title سباكس - تشغيل مع سجلات تفصيلية
color 0A

echo.
echo ═══════════════════════════════════════════════════════════
echo            🚀 تشغيل نظام سباكس مع سجلات تفصيلية 🚀
echo ═══════════════════════════════════════════════════════════
echo.
echo سيتم عرض جميع السجلات التفصيلية لتشخيص المشاكل
echo.

REM Set logging level to DEBUG for detailed logs
set PYTHONUNBUFFERED=1
set LOG_LEVEL=DEBUG

python START.py

echo.
echo ═══════════════════════════════════════════════════════════
echo                    انتهى البرنامج
echo ═══════════════════════════════════════════════════════════
echo.
pause
