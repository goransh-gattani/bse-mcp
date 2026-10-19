#!/bin/sh
# Double-click on a Mac: installs bse-mcp, connects it to Claude Desktop (and Claude Code if
# present), and restarts Claude Desktop so the BSE tools show up. Safe to run again (it upgrades).
# The first time, macOS may say it's from an unidentified developer: right-click the file > Open > Open.
cd "$HOME" || exit 1
echo "Connecting BSE to Claude..."
echo

if ! curl -LsSf https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.sh | sh; then
  echo
  echo "Something went wrong (see above). Nothing in Claude was changed unless it says so."
  echo "Press Enter to close."; read -r _; exit 1
fi

echo
if pgrep -xq Claude; then
  printf "Restart Claude Desktop now to load the BSE tools? Unsent text in Claude will be lost. [Y/n] "
  read -r ans
  case "$ans" in n*|N*) echo "OK. Quit Claude (Cmd+Q) and reopen it when you're ready." ;;
    *) osascript -e 'quit app "Claude"' >/dev/null 2>&1
       for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -xq Claude || break; sleep 1; done
       open -a Claude && echo "Claude Desktop restarted." ;;
  esac
elif [ -d "/Applications/Claude.app" ] || [ -d "$HOME/Applications/Claude.app" ]; then
  open -a Claude && echo "Opened Claude Desktop."
else
  echo "Claude Desktop isn't installed in Applications; get it from https://claude.ai/download"
  echo "and the BSE tools will be there when you open it."
fi
echo
echo "Try asking Claude: \"What's ABB India's latest quarterly result and how does it compare with last year?\""
echo "Press Enter to close."; read -r _
