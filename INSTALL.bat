@echo off
chcp 65001 >nul
echo ============================================================
echo SPX Smart - تثبيت المكتبات
echo ============================================================
echo.
echo جاري تثبيت المكتبات المطلوبة...
echo.

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

echo.
echo ============================================================
echo ✅ اكتمل التثبيت!
echo ============================================================
echo.
echo الآن يمكنك تشغيل النظام:
echo   - RUN.bat (تشغيل مباشر)
echo   - python START.py (تشغيل يدوي)
echo.
pause
