@echo off
REM Polygon Data Server - Windows Quick Start

echo.
echo =====================================================
echo       Polygon Data Server v1.0
echo     REST API + WebSocket Streaming
echo =====================================================
echo.

REM Save current directory and change to project root
set ORIGINAL_DIR=%CD%
cd /d C:\Users\codyc\AlphaXIII_V2

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Show menu
echo Select operation:
echo.
echo   1. Start server (normal mode)
echo   2. Start server (development mode with auto-reload)
echo   3. Test server connection
echo   4. Install dependencies
echo   5. View server logs
echo   6. Exit
echo.

set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" (
    echo.
    echo Starting Polygon Data Server...
    echo.
    echo =====================================================
    echo Server logs will appear below
    echo Press Ctrl+C to stop the server
    echo =====================================================
    echo.
    REM Run from project root using -m flag
    cmd /k python -m polygon.polygon_server.start_server
) else if "%choice%"=="2" (
    echo.
    echo Starting server in development mode...
    echo.
    echo =====================================================
    echo Server logs will appear below (auto-reload enabled)
    echo Press Ctrl+C to stop the server
    echo =====================================================
    echo.
    REM Run from project root with reload flag
    cmd /k python -m polygon.polygon_server.start_server --reload
) else if "%choice%"=="3" (
    echo.
    echo Testing server connection...
    python -m polygon.polygon_server.start_server --test
    pause
    cd /d %ORIGINAL_DIR%
) else if "%choice%"=="4" (
    echo.
    echo Installing dependencies...
    python -m pip install -r polygon/polygon_server/requirements.txt
    echo.
    echo Dependencies installed!
    pause
    cd /d %ORIGINAL_DIR%
) else if "%choice%"=="5" (
    echo.
    echo Opening log file...
    if exist polygon_server.log (
        notepad polygon_server.log
    ) else (
        echo No log file found yet. Start the server first.
        pause
    )
    cd /d %ORIGINAL_DIR%
) else if "%choice%"=="6" (
    cd /d %ORIGINAL_DIR%
    exit /b 0
) else (
    echo Invalid choice!
    pause
    cd /d %ORIGINAL_DIR%
    exit /b 1
)