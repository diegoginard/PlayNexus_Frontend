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
echo  [3] Compilar ejecutables .exe para distribucion (dist/)
echo.
set /p opt="Opcion (1, 2 o 3, por defecto 1): "

if "%opt%"=="2" (
    call "%~dp0PlayNexus_Config.bat"
) else if "%opt%"=="3" (
    call "%~dp0build_executables.bat"
) else (
    call "%~dp0PlayNexus_Launcher.bat"
)
