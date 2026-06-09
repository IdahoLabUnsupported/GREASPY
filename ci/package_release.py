from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
OUT_PATH = DIST_DIR / "greaspy-release.zip"


def iter_release_files() -> list[Path]:
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "LICENSE",
        REPO_ROOT / "requirements.txt",
        REPO_ROOT / "requirements-build.txt",
        REPO_ROOT / "bin" / "GREASPY.exe",
    ]
    files.extend(sorted((REPO_ROOT / "tools").rglob("*.py")))
    files.extend(sorted((REPO_ROOT / "tools" / "data").rglob("*")))
    return [p for p in files if p.is_file()]


def main() -> None:
    DIST_DIR.mkdir(exist_ok=True)
    release_files = iter_release_files()
    if not release_files:
        raise RuntimeError("No release files found.")

    with ZipFile(OUT_PATH, "w", ZIP_DEFLATED) as zf:
        for path in release_files:
            zf.write(path, path.relative_to(REPO_ROOT))

    print(f"Wrote {OUT_PATH}")
    print(f"Packaged {len(release_files)} files.")


if __name__ == "__main__":
    main()

