from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project import VrewError


APP_DATA_NAME = "Vrew 자동 편집기"
TOOLS_NAME = "ffmpeg"
DOWNLOAD_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class DownloadSpec:
    url: str
    binary_name: str
    sha256: str | None = None
    checksum_url: str | None = None


def managed_tool_directory() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / APP_DATA_NAME / TOOLS_NAME


def _binary_filename(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _candidate_paths(name: str) -> list[Path]:
    filename = _binary_filename(name)
    candidates: list[Path] = []

    configured = os.environ.get("VREW_FFMPEG_DIR")
    if configured:
        candidates.append(Path(configured).expanduser() / filename)

    candidates.append(managed_tool_directory() / filename)

    found = shutil.which(name)
    if found:
        candidates.append(Path(found))

    executable_directory = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_directory / filename,
            Path("/opt/homebrew/bin") / filename,
            Path("/usr/local/bin") / filename,
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            unique.append(candidate)
    return unique


def resolve_binary(name: str) -> str | None:
    candidates = _candidate_paths(name)
    return str(candidates[0]) if candidates else None


def dependency_status() -> dict[str, Any]:
    ffmpeg = resolve_binary("ffmpeg")
    ffprobe = resolve_binary("ffprobe")
    managed = managed_tool_directory()
    return {
        "ready": bool(ffmpeg and ffprobe),
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "managedDirectory": str(managed),
        "source": "managed" if ffmpeg and ffprobe and _is_managed(ffmpeg, ffprobe) else "system",
    }


def _is_managed(*paths: str) -> bool:
    managed = managed_tool_directory().resolve()
    return all(Path(path).resolve().parent == managed for path in paths)


def _download_specs() -> tuple[DownloadSpec, ...]:
    machine = platform.machine().casefold()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return (
            DownloadSpec(
                url="https://www.osxexperts.net/ffmpeg81arm.zip",
                binary_name="ffmpeg",
                sha256="ebb82529562b71170807bbc6b0e7eb4f0b13af8cbb0e085bb9e8f6fe709598ad",
            ),
            DownloadSpec(
                url="https://www.osxexperts.net/ffprobe81arm.zip",
                binary_name="ffprobe",
                sha256="a6640a77d38a6f0527c5b597e599cb36a3427a6931444ed80bc62542421950a1",
            ),
        )
    if sys.platform == "darwin" and machine in {"x86_64", "amd64"}:
        return (
            DownloadSpec(
                url="https://evermeet.cx/ffmpeg/ffmpeg-8.1.2.zip",
                binary_name="ffmpeg",
                sha256="e91df72a1ee7c26606f90dd2dd4dcccc6a75140ff9ea6fdd50faae828b82ba69",
            ),
            DownloadSpec(
                url="https://evermeet.cx/ffmpeg/ffprobe-8.1.2.zip",
                binary_name="ffprobe",
                sha256="399b93f0b9862f69767afa343e90c2f48d7e7958cadbb6deb76a012d0e3b7ce3",
            ),
        )
    if sys.platform == "win32" and machine in {"amd64", "x86_64", "x64"}:
        return (
            DownloadSpec(
                url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                binary_name="ffmpeg.exe",
                checksum_url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
            ),
            DownloadSpec(
                url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                binary_name="ffprobe.exe",
                checksum_url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
            ),
        )
    raise VrewError(
        f"현재 운영체제에서 FFmpeg 자동 설치를 지원하지 않습니다: "
        f"{sys.platform}/{machine}"
    )


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": "VrewAutoEditor/0.2.2"},
    )


def _download(url: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(
            _request(url), timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        raise VrewError(f"FFmpeg 다운로드에 실패했습니다: {exc}") from exc


def _checksum_from_url(url: str) -> str:
    try:
        with urllib.request.urlopen(
            _request(url), timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as exc:
        raise VrewError(f"FFmpeg 체크섬을 확인하지 못했습니다: {exc}") from exc
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise VrewError("FFmpeg 체크섬 응답이 올바르지 않습니다.")
    return match.group(1).lower()


def _verify_checksum(archive: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected.casefold():
        raise VrewError("다운로드한 FFmpeg 파일의 무결성 검증에 실패했습니다.")


def _extract_binary(archive: Path, binary_name: str, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as source:
            member = next(
                (
                    name
                    for name in source.namelist()
                    if Path(name).name.casefold() == binary_name.casefold()
                ),
                None,
            )
            if not member:
                raise VrewError(
                    f"FFmpeg 압축 파일에서 {binary_name}을 찾지 못했습니다."
                )
            destination.write_bytes(source.read(member))
    except zipfile.BadZipFile as exc:
        raise VrewError("다운로드한 FFmpeg 압축 파일이 손상되었습니다.") from exc
    if sys.platform != "win32":
        mode = destination.stat().st_mode
        destination.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_dependencies() -> dict[str, Any]:
    current = dependency_status()
    if current["ready"]:
        return {**current, "installed": False}

    specs = _download_specs()
    managed = managed_tool_directory()
    managed.parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix="vrew-ffmpeg-", dir=managed.parent
        ) as temporary:
            temporary_path = Path(temporary)
            archives: dict[str, Path] = {}
            for index, spec in enumerate(specs):
                archive = archives.get(spec.url)
                if archive is None:
                    archive = temporary_path / f"ffmpeg-{index}.zip"
                    _download(spec.url, archive)
                    expected = spec.sha256 or _checksum_from_url(
                        spec.checksum_url or ""
                    )
                    _verify_checksum(archive, expected)
                    archives[spec.url] = archive

                extracted = temporary_path / spec.binary_name
                _extract_binary(archive, spec.binary_name, extracted)
                target = managed / spec.binary_name
                managed.mkdir(parents=True, exist_ok=True)
                os.replace(extracted, target)
    except VrewError:
        raise
    except OSError as exc:
        raise VrewError(f"FFmpeg 설치 폴더를 준비하지 못했습니다: {exc}") from exc

    installed = dependency_status()
    if not installed["ready"]:
        raise VrewError(
            "FFmpeg 설치는 완료됐지만 실행 파일을 확인하지 못했습니다."
        )
    return {**installed, "installed": True}
