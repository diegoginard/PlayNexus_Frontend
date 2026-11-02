@echo off
cd /d "%~dp0"

echo ===================================================
echo             PlayNexus - Launcher
echo ===================================================
echo.
echo Selecciona el modo que deseas iniciar:
echo.
echo  [1] Iniciar Frontend de Juegos (Jugar)
echo  [2] Abrir Configurador (Listas, Emuladores, Layouts)
echo.
set /p opt="Opcion (1 o 2, por defecto 1): "

if "%opt%"=="2" (
    call "%~dp0PlayNexus_Config.bat"
) else (
    call "%~dp0PlayNexus_Launcher.bat"
)
