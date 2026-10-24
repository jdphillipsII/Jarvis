@echo off
rem Opens a JARVIS window on Windows. The Linux twin is `jarvis-window`.
rem
rem   jarvis-window.cmd app         a normal application window
rem   jarvis-window.cmd companion   a small window to pin
rem
rem Same reasoning as the Linux side: the page is already served on loopback,
rem so a browser in app mode is a real window with its own taskbar entry and
rem no second runtime. Windows 10+ ships curl.exe, so nothing extra is needed.
setlocal
set "MODE=%~1"
if "%MODE%"=="" set "MODE=app"
if "%JARVIS_PORT%"=="" set "JARVIS_PORT=8787"
set "URL=http://127.0.0.1:%JARVIS_PORT%/"

if /i "%MODE%"=="app"       ( set "CLASS=jarvis"           & set "SIZE=1280,860" )
if /i "%MODE%"=="companion" ( set "CLASS=jarvis-companion"  & set "SIZE=460,720"  )
if not defined CLASS ( echo usage: jarvis-window.cmd [app^|companion] & exit /b 2 )

call :awake && goto :open

rem Clicking an icon should start the app, not send you to a terminal.
set "LAUNCHER=%LOCALAPPDATA%\Programs\jarvis\jarvis.cmd"
if not exist "%LAUNCHER%" (
  echo JARVIS is not installed yet.
  echo   python cli.py link
  echo   jarvis install
  exit /b 1
)
start "" /min "%LAUNCHER%" serve
for /l %%i in (1,1,24) do (
  timeout /t 1 /nobreak >nul
  call :awake && goto :open
)
echo JARVIS did not come up on %JARVIS_PORT%.
echo   run it in the foreground to see why:  jarvis serve
exit /b 1

:open
set "PROFILE=%LOCALAPPDATA%\jarvis\%CLASS%"
for %%B in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) do (
  if exist %%B (
    start "" %%B --app="%URL%" --window-size=%SIZE% --user-data-dir="%PROFILE%"
    exit /b 0
  )
)
echo No Chrome or Edge found. Open %URL% yourself.
exit /b 1

:awake
curl -sf --max-time 1 "%URL%api/state" >nul 2>&1
exit /b %errorlevel%
