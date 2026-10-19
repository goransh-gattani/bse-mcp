"""`bse-mcp setup` must never lose the user's other Claude Desktop servers."""
import json
from pathlib import Path

import pytest

from bse_mcp import setup_claude as S


def test_config_paths():
    home = Path("/Users/me")
    assert S.desktop_config_path("darwin", home, {}) == home / "Library/Application Support/Claude/claude_desktop_config.json"
    assert S.desktop_config_path("win32", home, {"APPDATA": "C:/Users/me/AppData/Roaming"}) == Path("C:/Users/me/AppData/Roaming/Claude/claude_desktop_config.json")
    assert S.desktop_config_path("linux", home, {}) == home / ".config/Claude/claude_desktop_config.json"
    with pytest.raises(S.SetupError):
        S.desktop_config_path("win32", home, {})


def test_creates_config_when_missing(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    assert S.add_to_desktop_config(cfg, "/bin/bse-mcp") == "added"
    assert json.loads(cfg.read_text()) == {"mcpServers": {"bse": {"command": "/bin/bse-mcp"}}}
    assert not cfg.with_name(cfg.name + ".bak").exists()


def test_keeps_other_servers_and_settings(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    original = {"mcpServers": {"github": {"command": "npx", "args": ["gh-mcp"]}}, "globalShortcut": "Ctrl+Space"}
    cfg.write_text(json.dumps(original))
    assert S.add_to_desktop_config(cfg, "/bin/bse-mcp") == "added"
    now = json.loads(cfg.read_text())
    assert now["mcpServers"]["github"] == original["mcpServers"]["github"]
    assert now["globalShortcut"] == "Ctrl+Space"
    assert now["mcpServers"]["bse"] == {"command": "/bin/bse-mcp"}
    assert json.loads(cfg.with_name(cfg.name + ".bak").read_text()) == original


def test_idempotent_and_updates_path(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    S.add_to_desktop_config(cfg, "/old/bse-mcp")
    assert S.add_to_desktop_config(cfg, "/old/bse-mcp") == "unchanged"
    assert S.add_to_desktop_config(cfg, "/new/bse-mcp") == "updated"
    assert json.loads(cfg.read_text())["mcpServers"]["bse"] == {"command": "/new/bse-mcp"}


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"mcpServers": []}'])
def test_refuses_to_overwrite_a_broken_config(tmp_path, content):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(content)
    with pytest.raises(S.SetupError):
        S.add_to_desktop_config(cfg, "/bin/bse-mcp")
    assert cfg.read_text() == content


def test_empty_file_is_treated_as_new(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("  \n")
    assert S.add_to_desktop_config(cfg, "/bin/bse-mcp") == "added"
