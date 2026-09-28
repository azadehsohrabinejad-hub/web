@echo off
setlocal enabledelayedexpansion

set "app_dir=%~dp0"
set "backup_dir=%app_dir%backups"
if not exist "%backup_dir%" mkdir "%backup_dir%"

rem ── بکاپ روزانه دیتابیس (فایل .db) ──────────────────────
set "today=%date:~10,4%-%date:~7,2%-%date:~4,2%"
set "time=%time:~0,5%"
set "time=%time: =0%"
set "time=%time::=-%"

copy "%app_dir%shifts.db" "%backup_dir%\shifts_db_%today%_%time%.db" >nul

rem ── بکاپ هفتگی به صورت اکسل (فقط شیفت‌های این هفته) ─────
rem (هر شنبه ساعت 02:30 یک فایل اکسل از کل شیفت‌های هفته جاری می‌سازد)

wmic os get localdatetime | find "." > "%temp%\dt.txt"
for /f %%a in (%temp%\dt.txt) do set dt=%%a
set "year=!dt:~0,4!"
set "month=!dt:~4,2!"
set "day=!dt:~6,2!"
set "weekday=%date:~0,3%"

rem اگر امروز شنبه است → بکاپ هفتگی اکسل بگیر
if /i "%weekday%"=="Sat" (
    echo در حال ساخت بکاپ هفتگی اکسل از شیفت‌های این هفته...
    "%app_dir%venv\Scripts\python.exe" "%app_dir%weekly_excel_backup.py"
    echo بکاپ هفتگی اکسل با موفقیت ساخته شد
)

rem ── ثبت لاگ ─────────────────────────────────────
echo [%date% %time%] بکاپ روزانه + هفتگی (اگر شنبه باشد) انجام شد >> "%backup_dir%\backup_log.txt"
echo بکاپ موفق در %date% %time%
