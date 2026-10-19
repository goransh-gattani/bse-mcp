# bse-mcp installer for Windows (PowerShell).
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.ps1 | iex"
#
# 1. installs uv (https://docs.astral.sh/uv/) if it isn't there; uv fetches its own Python
# 2. installs bse-mcp (with curl_cffi) as a uv tool
# 3. checks that BSE answers from this network
# 4. registers the server with Claude Desktop (config merged, old file kept as .bak)
#    and with Claude Code if it is installed
#
# Re-running it upgrades bse-mcp. $env:BSE_MCP_SOURCE overrides what gets installed.
$ErrorActionPreference = "Stop"
$Source = if ($env:BSE_MCP_SOURCE) { $env:BSE_MCP_SOURCE } else { "git+https://github.com/goransh-gattani/bse-mcp" }
function Say($m) { Write-Host "`n==> $m" }
function Die($m) { Write-Host "`nbse-mcp install failed: $m" -ForegroundColor Red; exit 1 }

Say "Checking for uv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "uv not found; installing it"
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Die "uv installed but not found; open a new PowerShell window and run this again" }
}
uv --version

Say "Installing bse-mcp (with its own Python 3.12)"
uv tool install --force --python 3.12 "bse-mcp[chrome] @ $Source"
if ($LASTEXITCODE -ne 0) { Die "uv tool install failed" }
$Bin = (uv tool dir --bin).Trim()
$env:Path = "$Bin;$env:Path"
if (-not (Get-Command bse-mcp -ErrorAction SilentlyContinue)) { Die "bse-mcp was installed but isn't in $Bin" }
bse-mcp --version

Say "Checking that BSE answers from this network"
$Diag = (bse-mcp --diag 2>&1 | Out-String)
Write-Host $Diag
if ($Diag -match "HTTP 200") { Write-Host "OK: BSE answered." }
else {
  Write-Host "WARNING: BSE did not answer with HTTP 200 from this network. The tools will report the refusal;"
  Write-Host "         setup continues so you can retry later without reinstalling."
}

Say "Registering with Claude"
bse-mcp setup
if ($LASTEXITCODE -ne 0) { Die "setup failed (see the message above)" }

Write-Host @"

Done. Quit Claude Desktop completely (File > Exit, or right-click its tray icon > Quit) and reopen it, then ask e.g.
  "What's ABB India's latest quarterly result and how does it compare with last year?"
Claude asks permission the first time it uses a BSE tool.
"@
