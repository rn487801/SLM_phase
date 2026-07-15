@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [error] Python was not found on PATH. Install Python 3.9+ from python.org and try again.
    pause
    exit /b 1
)

python -c "import numpy, scipy, PIL, tkinter" >nul 2>nul
if errorlevel 1 (
    echo Installing required packages: numpy, scipy, pillow ...
    python -m pip install --quiet numpy scipy pillow
    if errorlevel 1 (
        echo [error] Failed to install required packages.
        pause
        exit /b 1
    )
)

python "%~dp0phase_gui.py" %*
if errorlevel 1 (
    echo.
    echo [error] phase_gui.py exited with an error.
    pause
)

endlocal
