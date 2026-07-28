from __future__ import annotations

import copy
import hashlib
import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterable


SUPPORTED_PROJECT_VERSIONS = {16, 17}


class VrewError(RuntimeError):
    """Raised when a Vrew project cannot be safely processed."""


def short_id(length: int = 10) -> str:
    """Return a Vrew-compatible URL-safe id."""
    return uuid.uuid4().hex[:length]


def uuid_id() -> str:
    return str(uuid.uuid4())


def _integrity_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    for info in payload.get("files", []):
        info.pop("path", None)
    payload["integrity"] = ""
    return payload


def compute_integrity(data: dict[str, Any]) -> str:
    """Reproduce Vrew 4.3.x's SHA-256 integrity calculation."""
    raw = json.dumps(
        _integrity_payload(data),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_integrity(data: dict[str, Any]) -> bool | None:
    expected = data.get("integrity")
    if not expected:
        return None
    return expected == compute_integrity(data)


@dataclass
class PendingMedia:
    archive_name: str
    source_path: Path | None = None
    data: bytes | None = None


@dataclass
class VrewProject:
    source_path: Path
    data: dict[str, Any]
    pending_media: list[PendingMedia] = field(default_factory=list)

    @classmethod
    def load(cls, source_path: str | Path) -> "VrewProject":
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise VrewError(f"Vrew 파일을 찾을 수 없습니다: {source}")
        if not zipfile.is_zipfile(source):
            raise VrewError(f"ZIP 기반 Vrew 프로젝트가 아닙니다: {source}")
        try:
            with zipfile.ZipFile(source) as archive:
                raw = archive.read("project.json")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise VrewError("project.json을 읽을 수 없는 Vrew 파일입니다.") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VrewError("project.json이 올바른 JSON이 아닙니다.") from exc

        version = data.get("version")
        if version not in SUPPORTED_PROJECT_VERSIONS:
            raise VrewError(
                f"검증되지 않은 Vrew 프로젝트 버전입니다: {version} "
                f"(지원: {sorted(SUPPORTED_PROJECT_VERSIONS)})"
            )
        if not isinstance(data.get("transcript", {}).get("clips"), list):
            raise VrewError("transcript.clips가 없는 프로젝트입니다.")
        if not isinstance(data.get("props", {}).get("tracks"), dict):
            raise VrewError("props.tracks가 없는 프로젝트입니다.")
        if not isinstance(data.get("props", {}).get("assets"), dict):
            raise VrewError("props.assets가 없는 프로젝트입니다.")
        return cls(source, data)

    @property
    def clips(self) -> list[dict[str, Any]]:
        return self.data["transcript"]["clips"]

    @property
    def tracks(self) -> dict[str, dict[str, Any]]:
        return self.data["props"]["tracks"]

    @property
    def assets(self) -> dict[str, dict[str, Any]]:
        return self.data["props"]["assets"]

    @property
    def files(self) -> list[dict[str, Any]]:
        return self.data["files"]

    def add_media(self, source_path: str | Path, media_id: str | None = None) -> str:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise VrewError(f"미디어 파일을 찾을 수 없습니다: {source}")
        media_id = media_id or uuid_id()
        suffix = source.suffix.lower()
        if suffix == ".jpg":
            suffix = ".jpeg"
        self.pending_media.append(
            PendingMedia(f"media/{media_id}{suffix}", source_path=source)
        )
        return media_id

    def add_embedded_media(self, archive_name: str, data: bytes) -> None:
        if not archive_name.startswith("media/"):
            raise VrewError(f"잘못된 Vrew 미디어 경로입니다: {archive_name}")
        self.pending_media.append(PendingMedia(archive_name, data=data))

    def save(self, output_path: str | Path) -> Path:
        output = Path(output_path).expanduser().resolve()
        if output == self.source_path:
            raise VrewError("원본 파일에는 덮어쓸 수 없습니다. 다른 출력 경로를 선택하세요.")
        if output.exists():
            raise VrewError(f"출력 파일이 이미 존재합니다. 다른 이름을 선택하세요: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)

        self.data["integrity"] = compute_integrity(self.data)
        project_json = json.dumps(
            self.data,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        temp_handle = tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-",
            suffix=".vrew",
            dir=output.parent,
            delete=False,
        )
        temp_path = Path(temp_handle.name)
        temp_handle.close()
        try:
            with zipfile.ZipFile(self.source_path, "r") as source_zip:
                with zipfile.ZipFile(temp_path, "w", allowZip64=True) as output_zip:
                    output_zip.comment = source_zip.comment
                    for info in source_zip.infolist():
                        if info.filename == "project.json":
                            new_info = copy.copy(info)
                            output_zip.writestr(new_info, project_json)
                            continue
                        with source_zip.open(info) as src, output_zip.open(
                            copy.copy(info), "w"
                        ) as dst:
                            shutil.copyfileobj(src, dst, length=1024 * 1024)

                    for pending in self.pending_media:
                        new_info = zipfile.ZipInfo(pending.archive_name)
                        new_info.compress_type = zipfile.ZIP_STORED
                        if pending.data is not None:
                            output_zip.writestr(new_info, pending.data)
                        elif pending.source_path is not None:
                            with pending.source_path.open(
                                "rb"
                            ) as src, output_zip.open(
                                new_info, "w", force_zip64=True
                            ) as dst:
                                shutil.copyfileobj(src, dst, length=1024 * 1024)
                        else:
                            raise VrewError(
                                f"내용이 없는 미디어 항목입니다: {pending.archive_name}"
                            )
            temp_path.replace(output)
            output.chmod(stat.S_IMODE(self.source_path.stat().st_mode))
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return output


def clip_caption(clip: dict[str, Any]) -> str:
    parts: list[str] = []
    for caption in clip.get("captions", []):
        for op in caption.get("text", []):
            insert = op.get("insert")
            if isinstance(insert, str):
                parts.append(insert)
    return "".join(parts).strip()


def clip_duration(clip: dict[str, Any]) -> float:
    return sum(float(word.get("duration", 0) or 0) for word in clip.get("words", []))


def add_asset_to_clips(
    clips: Iterable[dict[str, Any]], asset_id: str
) -> None:
    for clip in clips:
        asset_ids = clip.setdefault("assetIds", [])
        if asset_id not in asset_ids:
            asset_ids.append(asset_id)
