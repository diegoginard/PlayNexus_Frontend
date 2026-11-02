@echo off
cd /d "%~dp0"

echo ===================================================
echo             PlayNexus - Modo Frontend
echo ===================================================

if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creando entorno virtual Python en .venv...
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        python -m venv .venv
    ) else (
        where py >nul 2>nul
        if %errorlevel% equ 0 (
            py -3 -m venv .venv
        ) else (
            echo [ERROR] No se encontro Python en el sistema o no esta en el PATH.
            pause
            exit /b 1
        )
    )
    call .venv\Scripts\activate.bat
    python -m pip install --quiet -r requirements.txt
    echo [*] Entorno virtual creado exitosamente.
)

call .venv\Scripts\activate.bat

echo [*] Iniciando Frontend de Juegos...
"%~dp0.venv\Scripts\python.exe" -m playnexus --player

if %errorlevel% neq 0 if %errorlevel% neq -805306369 if %errorlevel% neq 3221225477 if %errorlevel% neq -1073740771 if %errorlevel% neq 3221226525 (
    echo.
    echo [!] La aplicacion se cerro con codigo %errorlevel%.
    pause
)

