@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo     PlayNexus - Compilador de Ejecutables (.exe)
echo ===================================================
echo.

:: 1. Verificar o crear entorno virtual
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
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    python -m pip install --quiet pyinstaller
    echo [*] Entorno virtual creado exitosamente.
) else (
    call .venv\Scripts\activate.bat
)

:: 2. Asegurar que PyInstaller este instalado en el entorno
"%~dp0.venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Instalando PyInstaller en .venv...
    "%~dp0.venv\Scripts\python.exe" -m pip install --quiet pyinstaller
)

:: 3. Ejecutar el script de compilacion y empaquetado limpio
echo [*] Iniciando compilacion de PlayNexus_Config.exe y PlayNexus_Launcher.exe...
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0build_executables.py"

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo  [EXITO] Compilacion finalizada correctamente.
    echo  Los ejecutables y recursos se encuentran en:
    echo  %~dp0dist
    echo ===================================================
) else (
    echo.
    echo [ERROR] Ocurrio un error durante la compilacion.
)

echo.
pause
