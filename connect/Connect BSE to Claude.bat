@echo off
rem Double-click on Windows: installs bse-mcp, connects it to Claude Desktop (and Claude Code if
rem present), and restarts Claude Desktop so the BSE tools show up. Safe to run again (it upgrades).
rem If Windows SmartScreen warns, choose "More info" > "Run anyway".
echo Connecting BSE to Claude...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.ps1 | iex"
if errorlevel 1 (
  echo.
  echo Something went wrong, see above. Nothing in Claude was changed unless it says so.
  pause
  exit /b 1
)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-Process -Name Claude -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($p) {" ^
  "  $exe = $p.Path;" ^
  "  $a = Read-Host 'Restart Claude Desktop now to load the BSE tools? Unsent text in Claude will be lost. [Y/n]';" ^
  "  if ($a -notmatch '^[nN]') { Get-Process -Name Claude | Stop-Process -Force; Start-Sleep 2; Start-Process $exe; 'Claude Desktop restarted.' }" ^
  "  else { 'OK. Quit Claude (File > Exit) and reopen it when you are ready.' }" ^
  "} else {" ^
  "  $exe = Join-Path $env:LOCALAPPDATA 'AnthropicClaude\claude.exe';" ^
  "  if (Test-Path $exe) { Start-Process $exe; 'Opened Claude Desktop.' }" ^
  "  else { 'Open Claude Desktop (or get it from https://claude.ai/download); the BSE tools will be there.' }" ^
  "}"
echo.
echo Try asking Claude: "What's ABB India's latest quarterly result and how does it compare with last year?"
pause
