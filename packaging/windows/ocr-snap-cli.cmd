@echo off
rem OCR Snap with a console: the same interpreter and flags as
rem "OCR Snap.exe", but output stays in this window (--version,
rem --self-test, --setup-engine, troubleshooting).
setlocal
set "OCR_SNAP_BUNDLE=%~dp0"
set "OCR_SNAP_BUNDLE=%OCR_SNAP_BUNDLE:~0,-1%"
"%OCR_SNAP_BUNDLE%\python\python.exe" -s -E -B -X utf8 "%OCR_SNAP_BUNDLE%\src\main.py" %*
exit /b %ERRORLEVEL%
