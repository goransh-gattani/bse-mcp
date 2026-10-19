#!/bin/sh
# bse-mcp installer for macOS and Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.sh | sh
#
# 1. installs uv (https://docs.astral.sh/uv/) if it isn't there; uv fetches its own Python,
#    so the Python that came with your Mac (3.9, too old) is left alone
# 2. installs bse-mcp (with curl_cffi) as a uv tool
# 3. checks that BSE answers from this network
# 4. registers the server with Claude Desktop (config merged, old file kept as .bak)
#    and with Claude Code if it is installed
#
# Re-running it upgrades bse-mcp and leaves the config as it is.
# BSE_MCP_SOURCE overrides what gets installed (e.g. a local checkout path or a git ref).
set -eu

SOURCE="${BSE_MCP_SOURCE:-git+https://github.com/goransh-gattani/bse-mcp}"
ORIG_PATH="$PATH"
say() { printf '\n==> %s\n' "$1"; }
die() { printf '\nbse-mcp install failed: %s\n' "$1" >&2; exit 1; }

say "Checking for uv"
if ! command -v uv >/dev/null 2>&1; then
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    [ -x "$d/uv" ] && PATH="$d:$PATH" && export PATH
  done
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; installing it"
  command -v curl >/dev/null 2>&1 || die "curl is needed to install uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "uv install failed"
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; export PATH
  command -v uv >/dev/null 2>&1 || die "uv installed but not found on PATH; open a new terminal and run this again"
fi
uv --version

say "Installing bse-mcp (with its own Python 3.12)"
uv tool install --force --python 3.12 "bse-mcp[chrome] @ $SOURCE" || die "uv tool install failed"
BIN="$(uv tool dir --bin)"
PATH="$BIN:$PATH"; export PATH
command -v bse-mcp >/dev/null 2>&1 || die "bse-mcp was installed but isn't in $BIN"
bse-mcp --version

say "Checking that BSE answers from this network"
DIAG="$(bse-mcp --diag 2>&1 || true)"
printf '%s\n' "$DIAG"
if printf '%s' "$DIAG" | grep -q "HTTP 200"; then
  echo "OK: BSE answered."
else
  echo "WARNING: BSE did not answer with HTTP 200 from this network. The tools will report the refusal;"
  echo "         setup continues so you can retry later (e.g. on another network) without reinstalling."
fi

say "Registering with Claude"
bse-mcp setup || die "setup failed (see the message above)"

case ":$ORIG_PATH:" in
  *":$BIN:"*) ;;
  *) echo
     echo "Note: $BIN is not on your shell's PATH; run  uv tool update-shell  and open a new terminal"
     echo "      if you want to type bse-mcp yourself. Claude doesn't need this: it uses the full path." ;;
esac

cat <<'MSG'

Done. Quit Claude Desktop completely (Cmd+Q) and reopen it, then ask e.g.
  "What's ABB India's latest quarterly result and how does it compare with last year?"
Claude asks permission the first time it uses a BSE tool.
MSG
