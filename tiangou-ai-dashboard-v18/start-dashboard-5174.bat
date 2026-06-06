@echo off
setlocal
echo Starting Tiangou AI on http://127.0.0.1:5174/
echo.
call npm install
if errorlevel 1 goto :error
call npm run dev:5174
goto :end
:error
echo Dependency installation failed. Copy the error above and send it for diagnosis.
:end
pause
