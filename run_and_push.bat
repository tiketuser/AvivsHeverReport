@echo off
chcp 65001 >nul
cd /d "C:\Users\Aviv Nir\Desktop\Hever\AvivsHeverReport"

echo [%date% %time%] Starting Hever scraper...
echo [%date% %time%] Starting Hever scraper... >> run.log

set PYTHONUTF8=1
echo [%date% %time%] Running python scraper.py...
python scraper.py >> run.log 2>&1

if %errorlevel% neq 0 (
    echo [%date% %time%] Scraper failed, skipping git push.
    echo [%date% %time%] Scraper failed, skipping git push. >> run.log
    exit /b 1
)

echo [%date% %time%] Scraper finished successfully.
echo [%date% %time%] Pushing to GitHub... >> run.log
echo [%date% %time%] Pushing to GitHub...
git add docs/
git diff --staged --quiet || git commit -m "Weekly update: %date%"
git push >> run.log 2>&1

echo [%date% %time%] Done.
echo [%date% %time%] Done. >> run.log
