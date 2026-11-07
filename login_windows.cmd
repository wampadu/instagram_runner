@echo off
setlocal
cd /d "%~dp0"
echo.
echo Instagram interactive login - credentials remain on this computer.
echo No proxy, no automated likes or follows.
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.12 from python.org and retry.
  pause
  exit /b 1
)
py -3.12 -m venv .venv-aiograpi
if errorlevel 1 (
  echo Could not create Python 3.12 environment.
  pause
  exit /b 1
)
".venv-aiograpi\Scripts\python.exe" -m pip install --disable-pip-version-check "https://codeload.github.com/subzeroid/aiograpi/zip/872039d37a61e5d60e07d47d3a230eafc23085e8"
if errorlevel 1 (
  echo Could not install the pinned open-source aiograpi revision.
  pause
  exit /b 1
)
echo.
echo Log in below. Enter your current verification code only when asked.
".venv-aiograpi\Scripts\python.exe" scripts\aiograpi_interactive_login.py
if errorlevel 1 (
  echo Login did not complete. Do not rerun repeatedly after rejection.
  pause
  exit /b 1
)
echo.
echo Login verified and local session saved. Keep it private.
pause
