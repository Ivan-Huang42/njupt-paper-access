from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "njupt-paper-access"
REQUIRED = [
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
    SKILL / "scripts" / "njupt-paper.ps1",
    SKILL / "scripts" / "njupt_paper.py",
]

for path in REQUIRED:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")

text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
match = re.match(r"^---\n(.*?)\n---", text, flags=re.DOTALL)
if not match:
    raise SystemExit("SKILL.md has no YAML frontmatter")

metadata = yaml.safe_load(match.group(1))
if metadata.get("name") != "njupt-paper-access":
    raise SystemExit("Unexpected skill name")
if not isinstance(metadata.get("description"), str):
    raise SystemExit("Skill description is missing")

for forbidden in ("password", "cookie", "api_key"):
    if forbidden in text.casefold() and "do not" not in text.casefold():
        raise SystemExit(f"Unexpected sensitive-data reference: {forbidden}")

print("Skill metadata is valid")
