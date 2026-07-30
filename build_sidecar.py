from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def host_triple() -> str:
    result = subprocess.run(
        ["rustc", "--print", "host-tuple"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    return result.stdout.strip()


def main() -> None:
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller가 필요합니다: python3 -m pip install pyinstaller"
        ) from exc

    build_root = ROOT / "build" / "sidecar"
    dist_root = build_root / "dist"
    work_root = build_root / "work"
    spec_root = build_root / "spec"
    binary_name = "vrew-engine"
    PyInstaller.__main__.run(
        [
            str(ROOT / "engine_main.py"),
            "--onefile",
            "--clean",
            "--noconfirm",
            "--name",
            binary_name,
            "--distpath",
            str(dist_root),
            "--workpath",
            str(work_root),
            "--specpath",
            str(spec_root),
        ]
    )

    extension = ".exe" if sys.platform == "win32" else ""
    source = dist_root / f"{binary_name}{extension}"
    destination = (
        ROOT
        / "src-tauri"
        / "binaries"
        / f"{binary_name}-{host_triple()}{extension}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    print(f"Tauri sidecar: {destination}")


if __name__ == "__main__":
    main()
