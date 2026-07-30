from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from .project import VrewError


def _run(command: list[str]) -> str | None:
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
    )
    stdout = result.stdout.decode("utf-8-sig", errors="replace")
    stderr = result.stderr.decode("utf-8-sig", errors="replace")
    if result.returncode != 0:
        # Cancel is not an application error.
        combined = f"{stdout}\n{stderr}".casefold()
        if "cancel" in combined or result.returncode == 1:
            return None
        raise VrewError(stderr.strip() or "경로 선택창을 열지 못했습니다.")
    try:
        value = result.stdout.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise VrewError("경로 선택 결과가 UTF-8이 아닙니다.") from exc
    return value or None


def _mac_picker(kind: str, title: str, default_name: str | None) -> str | None:
    title = title.replace("\\", "").replace('"', "")
    if kind == "directory":
        expression = f'POSIX path of (choose folder with prompt "{title}")'
    elif kind == "save":
        safe_name = (default_name or "자동편집.vrew").replace('"', "")
        expression = (
            f'POSIX path of (choose file name with prompt "{title}" '
            f'default name "{safe_name}")'
        )
    else:
        expression = f'POSIX path of (choose file with prompt "{title}")'
    return _run(["osascript", "-e", expression])


def _windows_picker(
    kind: str, title: str, default_name: str | None
) -> str | None:
    title_ps = title.replace("'", "''")
    default_ps = (default_name or "자동편집.vrew").replace("'", "''")
    prefix = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    )
    if kind == "directory":
        script = (
            prefix
            + "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
            + f"$d.Description='{title_ps}';"
            + "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
            + "{Write-Output $d.SelectedPath}"
        )
    elif kind == "save":
        script = (
            prefix
            + "$d=New-Object System.Windows.Forms.SaveFileDialog;"
            + f"$d.Title='{title_ps}';$d.FileName='{default_ps}';"
            + "$d.Filter='Vrew project (*.vrew)|*.vrew|All files (*.*)|*.*';"
            + "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
            + "{Write-Output $d.FileName}"
        )
    else:
        script = (
            prefix
            + "$d=New-Object System.Windows.Forms.OpenFileDialog;"
            + f"$d.Title='{title_ps}';"
            + "$d.Filter='All supported files|*.vrew;*.txt;*.mp4;*.mov;*.png;*.jpg;*.jpeg|All files (*.*)|*.*';"
            + "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
            + "{Write-Output $d.FileName}"
        )
    return _run(["powershell.exe", "-NoProfile", "-STA", "-Command", script])


def _linux_picker(kind: str, title: str, default_name: str | None) -> str | None:
    executable = shutil.which("zenity")
    if not executable:
        raise VrewError("Linux 경로 선택에는 zenity가 필요합니다.")
    command = [executable, "--file-selection", f"--title={title}"]
    if kind == "directory":
        command.append("--directory")
    elif kind == "save":
        command.extend(["--save", "--confirm-overwrite"])
        if default_name:
            command.append(f"--filename={default_name}")
    return _run(command)


def pick_path(
    kind: str,
    *,
    title: str = "경로 선택",
    default_name: str | None = None,
) -> str | None:
    if kind not in {"file", "directory", "save"}:
        raise VrewError(f"지원하지 않는 선택창 종류입니다: {kind}")
    system = platform.system()
    if system == "Darwin":
        return _mac_picker(kind, title, default_name)
    if system == "Windows":
        return _windows_picker(kind, title, default_name)
    return _linux_picker(kind, title, default_name)
