from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ADDON_DIRNAME = "rizom_bridge_for_blender"
FILES_TO_INCLUDE = [
    "__init__.py",
    "rizomuv_bridge_helper.py",
    "README.md",
    "LICENSE",
]


def read_version() -> str:
    init_path = ROOT / "__init__.py"
    content = init_path.read_text(encoding="utf-8")
    marker = '"version": ('
    start = content.find(marker)
    if start == -1:
        raise RuntimeError("Could not find bl_info version in __init__.py")
    start += len(marker)
    end = content.find(")", start)
    if end == -1:
        raise RuntimeError("Could not parse bl_info version in __init__.py")
    version_tuple = content[start:end]
    parts = [part.strip() for part in version_tuple.split(",") if part.strip()]
    return ".".join(parts)


def build_zip() -> Path:
    version = read_version()
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / f"{ADDON_DIRNAME}-{version}.zip"

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in FILES_TO_INCLUDE:
            source = ROOT / relative_path
            if not source.exists():
                raise FileNotFoundError(f"Missing file for packaging: {source}")
            archive.write(source, arcname=f"{ADDON_DIRNAME}/{relative_path}")

    return zip_path


def main() -> None:
    zip_path = build_zip()
    print(f"Created addon package: {zip_path}")


if __name__ == "__main__":
    main()
