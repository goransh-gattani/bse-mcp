"""The trading skills: valid for Claude Code and the Claude app, pointing only at real tools, zipped as committed."""
import re
import zipfile
from pathlib import Path

import pytest

from bse_mcp import setup_claude

from .test_server import EXPECTED as TOOL_NAMES

ROOT = Path(__file__).resolve().parent.parent
SKILLS = setup_claude.packaged_skills()
NAMES = ["bse-mcp-fibonacci-trading", "bse-mcp-multi-timeframe-analysis", "bse-mcp-position-sizing", "bse-mcp-risk-reward-ratio",
         "bse-mcp-rsi-divergence", "bse-mcp-stop-loss-strategies", "bse-mcp-technical-analysis", "bse-mcp-trading-toolkit",
         "bse-mcp-trailing-stops"]


def test_all_nine_skills_ship():
    assert [p.name for p in SKILLS] == NAMES


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_fits_claude_code_and_the_claude_app(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    # name, then a double-quoted description with no quotes or escapes inside: valid YAML by construction
    m = re.match(r'---\nname: ([a-z0-9-]+)\ndescription: "([^"\\]+)"\n---\n', text)
    assert m, "frontmatter must be exactly a name line and a double-quoted description line"
    name, description = m.groups()
    assert name == skill.name and len(name) <= 64  # the Claude app rejects a folder name that differs from the skill name
    assert len(description) <= 200  # the Claude app's limit for skill descriptions
    assert "Bhala Srinivash" in (skill / "LICENSE-nse-trading-skills").read_text(encoding="utf-8")  # MIT notice travels with the copy
    assert not re.search(r"groww|yfinance", text, re.I)  # the originals' broker and yfinance steps are gone


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_points_only_at_real_tools_and_skills(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    tools = set(re.findall(r"`((?:get|search|list|analyze|download|call)_[a-z_]+|position_size)", text))
    assert tools and tools <= set(TOOL_NAMES), tools - set(TOOL_NAMES)
    assert set(re.findall(r"\bbse-mcp-[a-z-]*[a-z]\b", text)) <= set(NAMES)


def test_zips_match_the_skills():
    zips = ROOT / "skill-zips"
    assert sorted(p.stem for p in zips.glob("*.zip")) == NAMES, "run python scripts/build_skill_zips.py"
    for skill in SKILLS:
        with zipfile.ZipFile(zips / f"{skill.name}.zip") as z:
            assert z.namelist()[0] == skill.name + "/"  # the skill folder at the zip's root, as the Claude app wants
            got = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        want = {f"{skill.name}/{p.relative_to(skill).as_posix()}": p.read_bytes() for p in skill.rglob("*") if p.is_file()}
        assert got == want, f"{skill.name}.zip is stale: run python scripts/build_skill_zips.py"
