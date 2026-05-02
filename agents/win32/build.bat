@echo off
echo === HiveAgent Build ===
echo.

REM Check if cl.exe is available
where cl >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Setting up MSVC environment...
    call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
)

echo Compiling HiveAgent...
cl /EHsc /std:c++17 /await /I../shared HiveAgent.cpp Telemetry.cpp WifiManager.cpp DataPlane.cpp /link WindowsApp.lib wlanapi.lib iphlpapi.lib ws2_32.lib /Fe:HiveAgent.exe

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS - HiveAgent.exe built
    del *.obj 2>nul
) else (
    echo.
    echo BUILD FAILED
)

echo.
if "%1"=="--no-pause" goto :eof
pause
