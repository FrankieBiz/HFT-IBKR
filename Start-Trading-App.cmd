@echo off
setlocal
where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo Windows Subsystem for Linux is missing. Install Ubuntu with: wsl --install -d Ubuntu
  echo Then follow SETUP.md to clone HFT-IBKR into your Linux home folder.
  pause
  exit /b 2
)
echo Starting your local trading desk in WSL...
echo Keep this window open. Ctrl+C stops the app and its owned jobs.
wsl.exe -- bash -lc "cd ~/HFT-IBKR && ./scripts/run_app.sh"
if errorlevel 1 (
  echo.
  echo Launch failed. Confirm HFT-IBKR is in your default WSL distribution at ~/HFT-IBKR.
  echo In Ubuntu: cd ~/HFT-IBKR ^&^& git pull
  echo Then: ./scripts/run_app.sh
  pause
  exit /b 2
)
endlocal
