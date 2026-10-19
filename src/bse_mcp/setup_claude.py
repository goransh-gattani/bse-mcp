"""`bse-mcp setup`: register this server with Claude Desktop and Claude Code.

Claude Desktop reads its servers from claude_desktop_config.json. We add (or update) one entry,
"bse", pointing at the absolute path of this command, and leave everything else in the file as it
was. The old file is kept next to it as .bak. A file that isn't valid JSON is never overwritten:
we stop and say so, because guessing would lose the user's other servers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "bse"


class SetupError(RuntimeError):
    pass


def desktop_config_path(platform: str | None = None, home: Path | None = None, env: dict | None = None) -> Path:
    """Where Claude Desktop keeps its config on this OS."""
    platform = platform or sys.platform
    home = home or Path.home()
    env = os.environ if env is None else env
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if platform.startswith("win"):
        appdata = env.get("APPDATA")
        if not appdata:
            raise SetupError("APPDATA is not set, so the Claude Desktop config folder can't be found")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "Claude" / "claude_desktop_config.json"


def command_path() -> str:
    """Absolute path of the bse-mcp launcher Claude should start (Claude Desktop doesn't see the shell's PATH)."""
    found = shutil.which("bse-mcp")
    if found:
        return os.path.abspath(found)
    argv0 = Path(sys.argv[0])
    if argv0.name.startswith("bse-mcp") and argv0.exists():
        return str(argv0.absolute())
    raise SetupError("can't find the bse-mcp command; install it first (see the README) and run `bse-mcp setup` again")


def add_to_desktop_config(path: Path, command: str) -> str:
    """Add or update the "bse" entry in a Claude Desktop config. Returns 'added', 'updated' or 'unchanged'."""
    config: dict = {}
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text.strip():
            try:
                config = json.loads(text)
            except ValueError as exc:
                raise SetupError(f"{path} is not valid JSON ({exc}); fix or remove it, then run `bse-mcp setup` again") from None
            if not isinstance(config, dict):
                raise SetupError(f"{path} does not contain a JSON object; fix it, then run `bse-mcp setup` again")
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise SetupError(f'"mcpServers" in {path} is not an object; fix it, then run `bse-mcp setup` again')
    wanted = {"command": command}
    before = servers.get(SERVER_NAME)
    if before == wanted:
        return "unchanged"
    servers[SERVER_NAME] = wanted
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: Claude never sees a half-written file
    return "updated" if before is not None else "added"


def add_to_claude_code(command: str) -> str:
    """Register with Claude Code (user scope) if its CLI is installed. Returns a one-line status."""
    claude = shutil.which("claude")
    if not claude:
        return "Claude Code: not installed, skipped"
    # Re-adding an existing name fails, so remove first; a failed remove just means it wasn't there.
    subprocess.run([claude, "mcp", "remove", "--scope", "user", SERVER_NAME], capture_output=True, text=True)
    res = subprocess.run([claude, "mcp", "add", "--scope", "user", SERVER_NAME, "--", command], capture_output=True, text=True)
    if res.returncode != 0:
        raise SetupError(f"`claude mcp add` failed: {(res.stderr or res.stdout).strip()[:300]}")
    return "Claude Code: registered (user scope)"


def run(desktop: bool = True, code: bool = True) -> list[str]:
    command = command_path()
    lines = [f"bse-mcp command: {command}"]
    if desktop:
        path = desktop_config_path()
        state = add_to_desktop_config(path, command)
        lines.append(f"Claude Desktop: {state} in {path}")
        if state != "unchanged":
            lines.append("  -> quit Claude Desktop completely (Cmd+Q / File > Exit) and reopen it to load the tools")
    if code:
        lines.append(add_to_claude_code(command))
    return lines
