@echo off
setlocal
echo Starting Tiangou AI on http://127.0.0.1:5173/
echo.
call npm install
if errorlevel 1 goto :error
call npm run dev
if errorlevel 1 goto :porterror
goto :end

:porterror
echo.
echo The dashboard did not start. Port 5173 may already be used by an older Vite server.
echo Close the previous terminal window or run: taskkill /F /IM node.exe
echo Then launch this file again.
goto :end

:error
echo.
echo Dependency installation failed. Copy the error above and send it for diagnosis.

:end
pause
