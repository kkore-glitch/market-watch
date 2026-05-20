from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "handoff" / "market-watch-handoff.zip"
INCLUDE = [
    ".git",
    ".env.example",
    ".gitignore",
    "README.md",
    "config",
    "market_watch",
    "requirements.txt",
    "tools",
]
EXCLUDE_PARTS = {
    "__pycache__",
    ".venv",
    "reports",
    "handoff",
}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(part in EXCLUDE_PARTS for part in rel.parts) or path.name.endswith(".pyc")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for item in INCLUDE:
            path = ROOT / item
            if not path.exists():
                continue
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
                continue
            for child in path.rglob("*"):
                if child.is_file() and not should_skip(child):
                    archive.write(child, child.relative_to(ROOT))
    print(OUTPUT)


if __name__ == "__main__":
    main()
