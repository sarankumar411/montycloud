@echo off
REM Startup script for Image Upload Service (Windows)

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo Image Upload Service - Startup Script
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.7+ from https://www.python.org/
    pause
    exit /b 1
)

echo ✓ Python found: 
python --version

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Docker is not installed. LocalStack won't start.
    echo Please install Docker from https://www.docker.com/
) else (
    echo ✓ Docker found:
    docker --version
    
    REM Check if Docker daemon is running
    docker info >nul 2>&1
    if errorlevel 1 (
        echo ⚠️  Docker daemon is not running
        echo Please start Docker Desktop
    ) else (
        echo ✓ Docker daemon is running
    )
)

REM Create .env if it doesn't exist
if not exist ".env" (
    echo.
    echo Creating .env file from .env.example...
    copy .env.example .env >nul
    echo ✓ Created .env file
)

REM Install Python dependencies
echo.
echo Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Failed to install dependencies
    pause
    exit /b 1
)
echo ✓ Dependencies installed

REM Start LocalStack
if exist "docker-compose.yml" (
    echo.
    echo Starting LocalStack...
    docker-compose up -d
    
    REM Wait for LocalStack
    echo Waiting for LocalStack to be ready...
    timeout /t 5 /nobreak
    
    echo ✓ LocalStack started
) else (
    echo.
    echo ⚠️  docker-compose.yml not found, skipping LocalStack startup
)

REM Run tests (optional)
echo.
set /p run_tests="Run unit tests? (y/n): "
if /i "%run_tests%"=="y" (
    pytest test_app.py -v
)

REM Start the application
echo.
echo ==========================================
echo Starting Image Upload Service API
echo ==========================================
echo API will be available at: http://localhost:5000
echo Health check: http://localhost:5000/health
echo.
echo Press Ctrl+C to stop the server
echo.

python app.py

pause
