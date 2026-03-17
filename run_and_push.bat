@echo off
chcp 65001 >nul
cd /d "C:\Users\Aviv Nir\Desktop\Hever\AvivsHeverReport"

echo [%date% %time%] Starting Hever scraper... >> run.log

set PYTHONUTF8=1
python scraper.py >> run.log 2>&1

if %errorlevel% neq 0 (
    echo [%date% %time%] Scraper failed, skipping git push. >> run.log
    exit /b 1
)

echo [%date% %time%] Pushing to GitHub... >> run.log
git add docs/
git diff --staged --quiet || git commit -m "Weekly update: %date%"
git push >> run.log 2>&1

echo [%date% %time%] Done. >> run.log
