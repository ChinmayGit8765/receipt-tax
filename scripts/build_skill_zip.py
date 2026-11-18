#!/usr/bin/env python3
"""Package skill/receipt-tax (including your config.json) into dist/receipt-tax-skill.zip.

Uses forward-slash paths, which claude.ai's skill upload expects (Windows' built-in zip and
PowerShell 5's Compress-Archive write backslashes).
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "receipt-tax"
OUT = ROOT / "dist" / "receipt-tax-skill.zip"


def main():
    cfg = SKILL / "config.json"
    if not cfg.exists():
        sys.exit("error: create skill/receipt-tax/config.json first (copy config.example.json)")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    st = data.get("storage", {})
    if st.get("type") == "google" and ("YOUR_DEPLOYMENT_ID" in st.get("endpoint", "") or not st.get("token")):
        sys.exit("error: config.json still has the placeholder endpoint/token")
    if st.get("type", "local") == "local":
        print("warning: local storage does not persist in the Claude app; fine for Claude Code/Codex")

    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(SKILL.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.name != "config.example.json":
                z.write(p, Path("receipt-tax", p.relative_to(SKILL)).as_posix())
    print(f"{OUT}  (contains your token: keep it private)")


if __name__ == "__main__":
    main()
