@echo off
TITLE Prism Wallpapers Installer
echo ===================================================
echo      Prism Wallpapers - One-Click Installer
echo ===================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please download Python from python.org and ensure "Add python.exe to PATH" is checked.
    pause
    exit /b
)

echo [1/4] Creating isolated Python environment (venv)...
python -m venv venv

echo [2/4] Installing required libraries...
call venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

echo [3/4] Preparing API key files...
IF NOT EXIST ".env" (
    copy .env.example .env >nul
    echo   - Created default .env file.
) ELSE (
    echo   - .env file already exists, skipping.
)

echo [4/4] Creating Desktop Shortcut...
:: Use VBScript to create a clean shortcut on the user's desktop
set SCRIPT="%TEMP%\CreateShortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = "%USERPROFILE%\Desktop\Prism Wallpapers.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%~dp0venv\Scripts\pythonw.exe" >> %SCRIPT%
echo oLink.Arguments = """%~dp0scripts\gui_launcher.py""" >> %SCRIPT%
echo oLink.WorkingDirectory = "%~dp0" >> %SCRIPT%
echo oLink.IconLocation = "%~dp0venv\Scripts\python.exe, 0" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo ===================================================
echo SUCCESS! Prism Wallpapers has been installed.
echo You can now close this window and launch the app
echo using the 'Prism Wallpapers' shortcut on your Desktop.
echo ===================================================
pause