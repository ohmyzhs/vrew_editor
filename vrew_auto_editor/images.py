from __future__ import annotations

import hashlib
import random
import re
import struct
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .project import (
    VrewError,
    VrewProject,
    add_asset_to_clips,
    clip_caption,
    clip_duration,
    short_id,
    uuid_id,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

KEN_BURNS = {
    "bottom-to-top": {
        "type": "bottom-to-top",
        "from": {"scale": 0.7, "centerX": 0.5, "centerY": 0.58},
        "to": {"scale": 0.7, "centerX": 0.5, "centerY": 0.42},
    },
    "left-to-right": {
        "type": "left-to-right",
        "from": {"scale": 0.7, "centerX": 0.42, "centerY": 0.5},
        "to": {"scale": 0.7, "centerX": 0.58, "centerY": 0.5},
    },
    "right-to-left": {
        "type": "right-to-left",
        "from": {"scale": 0.7, "centerX": 0.58, "centerY": 0.5},
        "to": {"scale": 0.7, "centerX": 0.42, "centerY": 0.5},
    },
    "top-to-bottom": {
        "type": "top-to-bottom",
        "from": {"scale": 0.7, "centerX": 0.5, "centerY": 0.42},
        "to": {"scale": 0.7, "centerX": 0.5, "centerY": 0.58},
    },
    "zoom-in": {
        "type": "zoom-in",
        "from": {"scale": 0.77, "centerX": 0.5, "centerY": 0.5},
        "to": {"scale": 0.63, "centerX": 0.5, "centerY": 0.5},
    },
    "zoom-out": {
        "type": "zoom-out",
        "from": {"scale": 0.63, "centerX": 0.5, "centerY": 0.5},
        "to": {"scale": 0.77, "centerX": 0.5, "centerY": 0.5},
    },
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "".join(char.casefold() for char in text if char.isalnum())


def parse_numbered_script(text: str) -> dict[int, str]:
    """Parse the first occurrence of each `1. text` or `001) text` line."""
    result: dict[int, str] = {}
    for raw_line in text.splitlines():
        match = re.match(r"^\s*(\d{1,4})\s*[\.)]\s*(\S.*)$", raw_line)
        if not match:
            continue
        number = int(match.group(1))
        result.setdefault(number, match.group(2).strip())
    return result


def discover_numbered_images(
    directory: str | Path, preferred_variant: str = "1"
) -> tuple[dict[int, Path], dict[int, list[Path]]]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise VrewError(f"이미지 폴더를 찾을 수 없습니다: {root}")
    candidates: dict[int, list[Path]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        match = re.match(r"^(\d{1,4})(?:[-_](\d+))?", path.stem)
        if not match:
            continue
        candidates.setdefault(int(match.group(1)), []).append(path)

    selected: dict[int, Path] = {}
    conflicts: dict[int, list[Path]] = {}
    for number, paths in candidates.items():
        ordered = sorted(paths, key=lambda value: value.name.casefold())
        if len(ordered) > 1:
            conflicts[number] = ordered
        preferred = [
            path
            for path in ordered
            if re.match(
                rf"^{number:0{len(str(number))}d}[-_]{re.escape(preferred_variant)}(?:\D|$)",
                path.stem,
            )
            or re.match(
                rf"^0*{number}[-_]{re.escape(preferred_variant)}(?:\D|$)",
                path.stem,
            )
        ]
        selected[number] = preferred[0] if preferred else ordered[0]
    return selected, conflicts


def _transcript_index(clips: list[dict[str, Any]]) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    char_to_clip: list[int] = []
    for clip_index, clip in enumerate(clips):
        normalized = _normalize(clip_caption(clip))
        normalized_chars.extend(normalized)
        char_to_clip.extend([clip_index] * len(normalized))
    return "".join(normalized_chars), char_to_clip


@dataclass
class ScriptMatch:
    number: int
    text: str
    clip_index: int


def match_script_to_clips(
    clips: list[dict[str, Any]], script: dict[int, str]
) -> tuple[list[ScriptMatch], list[dict[str, Any]]]:
    haystack, char_to_clip = _transcript_index(clips)
    matches: list[ScriptMatch] = []
    unmatched: list[dict[str, Any]] = []
    cursor = 0
    for number in sorted(script):
        source = script[number]
        needle = _normalize(source)
        if not needle:
            unmatched.append({"number": number, "text": source, "reason": "empty"})
            continue
        position = haystack.find(needle, cursor)
        if position < 0:
            position = haystack.find(needle)
        if position < 0:
            unmatched.append(
                {"number": number, "text": source, "reason": "not found"}
            )
            continue
        clip_index = char_to_clip[position]
        matches.append(ScriptMatch(number, source, clip_index))
        cursor = position + len(needle)
    return matches, unmatched


def _jpeg_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        if file.read(2) != b"\xff\xd8":
            raise VrewError(f"올바른 JPEG가 아닙니다: {path.name}")
        while True:
            marker_start = file.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = file.read(1)
            while marker == b"\xff":
                marker = file.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_raw = file.read(2)
            if len(length_raw) != 2:
                break
            length = struct.unpack(">H", length_raw)[0]
            if marker and marker[0] in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                payload = file.read(5)
                if len(payload) != 5:
                    break
                height, width = struct.unpack(">HH", payload[1:])
                return width, height
            file.seek(length - 2, 1)
    raise VrewError(f"JPEG 크기를 읽을 수 없습니다: {path.name}")


def image_info(path: str | Path) -> tuple[int, int, bool]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        width, height = _jpeg_size(source)
        return width, height, False
    if suffix == ".png":
        with source.open("rb") as file:
            header = file.read(26)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            raise VrewError(f"올바른 PNG가 아닙니다: {source.name}")
        width, height = struct.unpack(">II", header[16:24])
        color_type = header[25]
        return width, height, color_type in {4, 6}
    if suffix == ".webp":
        raise VrewError(
            "WebP는 현재 크기 판독을 지원하지 않습니다. JPG 또는 PNG로 변환하세요."
        )
    raise VrewError(f"지원하지 않는 이미지 형식입니다: {source.suffix}")


def _fill_geometry(image_ratio: float, video_ratio: float) -> dict[str, float]:
    if image_ratio >= video_ratio:
        width = image_ratio / video_ratio
        return {
            "xPos": (1 - width) / 2,
            "yPos": 0,
            "height": 1,
            "width": width,
        }
    height = video_ratio / image_ratio
    return {
        "xPos": 0,
        "yPos": (1 - height) / 2,
        "height": height,
        "width": 1,
    }


def partition_clip_range(
    clips: list[dict[str, Any]],
    start: int,
    end: int,
    minimum: float = 15.0,
    maximum: float = 20.0,
) -> list[tuple[int, int, float]]:
    if start >= end:
        return []
    durations = [clip_duration(clip) for clip in clips[start:end]]
    prefix = [0.0]
    for duration in durations:
        prefix.append(prefix[-1] + duration)
    target = (minimum + maximum) / 2

    # Lexicographic cost: first avoid any out-of-range segment, then keep
    # segment lengths near the middle of the requested interval.
    best: list[tuple[int, float, int] | None] = [None] * (len(durations) + 1)
    best[0] = (0, 0.0, -1)
    for right in range(1, len(durations) + 1):
        candidate: tuple[int, float, int] | None = None
        for left in range(right):
            previous = best[left]
            if previous is None:
                continue
            duration = prefix[right] - prefix[left]
            violation = 0 if minimum <= duration <= maximum else 1
            score = (
                previous[0] + violation,
                previous[1] + (duration - target) ** 2,
                left,
            )
            if candidate is None or score[:2] < candidate[:2]:
                candidate = score
        best[right] = candidate

    boundaries: list[int] = [len(durations)]
    cursor = len(durations)
    while cursor > 0:
        item = best[cursor]
        if item is None:
            break
        cursor = item[2]
        boundaries.append(cursor)
    boundaries.reverse()
    segments: list[tuple[int, int, float]] = []
    for left, right in zip(boundaries, boundaries[1:]):
        segments.append(
            (start + left, start + right, prefix[right] - prefix[left])
        )
    return segments


class EffectBag:
    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        self.remaining: list[str] = []
        self.previous: str | None = None

    def next(self) -> str:
        if not self.remaining:
            self.remaining = list(KEN_BURNS)
            self.random.shuffle(self.remaining)
            if (
                self.previous
                and len(self.remaining) > 1
                and self.remaining[-1] == self.previous
            ):
                self.remaining[0], self.remaining[-1] = (
                    self.remaining[-1],
                    self.remaining[0],
                )
        value = self.remaining.pop()
        self.previous = value
        return value


def _register_image(
    project: VrewProject, path: Path
) -> tuple[str, float, bool]:
    width, height, transparent = image_info(path)
    media_id = project.add_media(path)
    project.files.append(
        {
            "version": 1,
            "mediaId": media_id,
            "sourceOrigin": "USER",
            "fileSize": path.stat().st_size,
            "name": f"{media_id}{path.suffix.lower()}",
            "type": "Image",
            "isTransparent": transparent,
            "fileLocation": "IN_MEMORY",
        }
    )
    return media_id, width / height, transparent


def _attach_image_segment(
    project: VrewProject,
    clip_slice: Iterable[dict[str, Any]],
    media_id: str,
    image_ratio: float,
    effect: str | None,
    import_type: str = "agent",
    z_index: int = 0,
) -> str:
    track_id = short_id()
    asset_id = uuid_id()
    video_ratio = float(project.data.get("props", {}).get("videoRatio", 16 / 9))
    geometry = _fill_geometry(image_ratio, video_ratio)
    track: dict[str, Any] = {
        "trackId": track_id,
        "mediaId": media_id,
        **geometry,
        "rotation": 0,
        "zIndex": z_index,
        "type": "image",
        "originalWidthHeightRatio": image_ratio,
        "importType": import_type,
        "editInfo": {},
        "stats": {"fillType": "cut", "isTransparent": False},
    }
    if effect:
        track["kenburnsAnimationInfo"] = KEN_BURNS[effect]
    project.tracks[track_id] = track
    project.assets[asset_id] = {"trackIds": [track_id], "role": "sub"}
    add_asset_to_clips(clip_slice, asset_id)
    return asset_id


def attach_numbered_images(
    project: VrewProject,
    script: dict[int, str],
    image_paths: dict[int, Path],
    *,
    seed: int = 20260728,
    minimum_seconds: float = 15.0,
    maximum_seconds: float = 20.0,
    coverage_end_clip: int | None = None,
    ken_burns: bool = True,
) -> dict[str, Any]:
    matches, unmatched_script = match_script_to_clips(project.clips, script)
    matched_with_images = [match for match in matches if match.number in image_paths]
    missing_images = [
        {"number": match.number, "text": match.text}
        for match in matches
        if match.number not in image_paths
    ]
    effect_bag = EffectBag(seed)
    registered: dict[Path, tuple[str, float, bool]] = {}
    placements: list[dict[str, Any]] = []
    pending_effects: list[tuple[str, str]] = []

    final_coverage_end = (
        len(project.clips)
        if coverage_end_clip is None
        else min(len(project.clips), coverage_end_clip)
    )
    matched_with_images = [
        match for match in matched_with_images if match.clip_index < final_coverage_end
    ]
    for index, match in enumerate(matched_with_images):
        end_clip = (
            matched_with_images[index + 1].clip_index
            if index + 1 < len(matched_with_images)
            else final_coverage_end
        )
        if end_clip <= match.clip_index:
            continue
        image_path = image_paths[match.number]
        if image_path not in registered:
            registered[image_path] = _register_image(project, image_path)
        media_id, image_ratio, _ = registered[image_path]
        segments = (
            partition_clip_range(
                project.clips,
                match.clip_index,
                end_clip,
                minimum_seconds,
                maximum_seconds,
            )
            if ken_burns
            else [
                (
                    match.clip_index,
                    end_clip,
                    sum(
                        clip_duration(clip)
                        for clip in project.clips[match.clip_index:end_clip]
                    ),
                )
            ]
        )
        placement_segments: list[dict[str, Any]] = []
        for start, end, duration in segments:
            effect = effect_bag.next() if ken_burns else None
            asset_id = _attach_image_segment(
                project,
                project.clips[start:end],
                media_id,
                image_ratio,
                None,
            )
            track_id = project.assets[asset_id]["trackIds"][0]
            if effect is not None:
                pending_effects.append((track_id, effect))
            placement_segments.append(
                {
                    "startClip": start + 1,
                    "endClip": end,
                    "duration": round(duration, 3),
                    "effect": effect,
                    "assetId": asset_id,
                }
            )
        placements.append(
            {
                "number": match.number,
                "image": str(image_path),
                "anchorClip": match.clip_index + 1,
                "endClip": end_clip,
                "segments": placement_segments,
            }
        )

    # Vrew agent의 안정적인 작업 순서와 동일하게 모든 이미지 구간을 먼저
    # 생성한 다음 애니메이션 속성을 한 번에 적용한다.
    for track_id, effect in pending_effects:
        project.tracks[track_id]["kenburnsAnimationInfo"] = KEN_BURNS[effect]

    return {
        "matchedScriptCount": len(matches),
        "placedImageCount": len(placements),
        "segmentCount": sum(len(item["segments"]) for item in placements),
        "kenBurnsEnabled": ken_burns,
        "batchAnimationCount": len(pending_effects),
        "coverageEndClip": final_coverage_end,
        "unmatchedScript": unmatched_script,
        "missingImages": missing_images,
        "placements": placements,
    }


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
