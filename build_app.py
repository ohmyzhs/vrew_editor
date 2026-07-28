from __future__ import annotations

import platform
import subprocess
import sys


def main() -> int:
    try:
        import PyInstaller.__main__  # type: ignore[import-not-found]
    except ImportError:
        print("PyInstaller가 필요합니다: python -m pip install pyinstaller")
        return 2

    name = "VrewAutoEditor"
    PyInstaller.__main__.run(
        [
            "run_gui.py",
            "--name",
            name,
            "--windowed",
            "--noconfirm",
            "--clean",
        ]
    )
    print(f"{platform.system()}용 앱 생성 완료: dist/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
