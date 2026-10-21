"""Rebuild skill-zips/: one zip per skill, for uploading to the Claude app (Customize > Skills > Upload a skill).

Run from anywhere after changing anything in src/bse_mcp/skills/:

    python scripts/build_skill_zips.py

tests/test_skills.py fails until the zips match the skill folders again.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "bse_mcp" / "skills"
OUT = ROOT / "skill-zips"


def entry(name: str, mode: int) -> zipfile.ZipInfo:
    # Fixed timestamp and Unix permissions, so rebuilding unchanged skills gives unchanged zips.
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system, info.external_attr = 3, mode << 16
    return info


def build(skill: Path, out: Path) -> None:
    """The Claude app wants the skill folder itself at the root of the zip."""
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(entry(skill.name + "/", 0o40755), b"")
        for p in sorted(p for p in skill.rglob("*") if p.is_file()):
            z.writestr(entry(f"{skill.name}/{p.relative_to(skill).as_posix()}", 0o100644), p.read_bytes(),
                       compress_type=zipfile.ZIP_DEFLATED)


def main() -> None:
    names = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.zip"):
        if old.stem not in names:
            old.unlink()
    for name in names:
        build(SKILLS / name, OUT / f"{name}.zip")
    print(f"wrote {len(names)} zips to {OUT}")


if __name__ == "__main__":
    main()
