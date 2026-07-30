from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .images import _register_image
from .project import (
    VrewError,
    VrewProject,
    add_asset_to_clips,
    clip_duration,
    short_id,
    uuid_id,
)


def attach_global_watermark(
    project: VrewProject,
    image_path: str | Path,
    *,
    width: float = 0.10,
    margin: float = 0.02,
    z_index: int = 399,
) -> str:
    source = Path(image_path).expanduser().resolve()
    media_id, image_ratio, _ = _register_image(project, source)
    track_id = short_id()
    asset_id = uuid_id()
    height = width / image_ratio / float(project.data["props"].get("videoRatio", 16 / 9))
    project.tracks[track_id] = {
        "trackId": track_id,
        "mediaId": media_id,
        "xPos": 1 - width - margin,
        "yPos": 1 - height - margin,
        "height": height,
        "width": width,
        "rotation": 0,
        "zIndex": z_index,
        "type": "image",
        "originalWidthHeightRatio": image_ratio,
        "importType": "user_asset_panel",
        "editInfo": {},
        "stats": {},
    }
    project.assets[asset_id] = {"trackIds": [track_id], "role": "sub"}
    add_asset_to_clips(project.clips, asset_id)
    return asset_id


def attach_ai_notice(
    project: VrewProject,
    text: str = "이 영상은 AI기술을 이용한 창작물입니다.",
    *,
    z_index: int = 400,
) -> str:
    track_id = short_id()
    asset_id = uuid_id()
    project.tracks[track_id] = {
        "trackId": track_id,
        "mediaId": "uc-0010-basic-text-01",
        "xPos": 0,
        "yPos": 0.02,
        "height": 0,
        "width": 0.3025,
        "rotation": 0,
        "zIndex": z_index,
        "type": "web",
        "deltas": {
            "textarea": {
                "ops": [
                    {
                        "insert": text,
                        "attributes": {
                            "size": "50",
                            "color": "#ffffff",
                            "font": "NanumSquare Neo Bold-Vrew_700",
                            "outline-color": "#000000",
                            "outline-width": "4",
                            "outline-on": "true",
                        },
                    },
                    {"insert": "\n"},
                ]
            }
        },
        "loop": False,
        "durationSeconds": 0,
        "importType": "unknown",
        "enabledInlineTypes": [
            "bold",
            "italic",
            "font",
            "size",
            "color",
            "outline-color",
            "background",
            "shadow-color",
        ],
        "customAttributes": [
            {
                "attributeName": "--textbox-align",
                "type": "textbox-align",
                "value": "center",
            }
        ],
        "stats": {"styledInFloatingMenu": True, "styledInPanel": False},
        "scaleFactor": float(project.data["props"].get("videoRatio", 16 / 9)),
    }
    project.assets[asset_id] = {"trackIds": [track_id], "role": "sub"}
    add_asset_to_clips(project.clips, asset_id)
    return asset_id


def probe_video(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    executable = shutil.which("ffprobe")
    if not executable:
        candidates = [
            Path(sys.executable).resolve().parent / "ffprobe",
            Path(sys.executable).resolve().parent / "ffprobe.exe",
            Path("/opt/homebrew/bin/ffprobe"),
            Path("/usr/local/bin/ffprobe"),
        ]
        executable = next(
            (str(candidate) for candidate in candidates if candidate.is_file()),
            None,
        )
    if not executable:
        raise VrewError(
            "인트로 영상 분석에 ffprobe가 필요합니다. FFmpeg를 설치하거나 "
            "ffprobe 실행 파일을 앱과 같은 폴더에 두세요."
        )
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source),
            ],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise VrewError(f"ffprobe를 실행하지 못했습니다: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        message = f"ffprobe가 영상을 분석하지 못했습니다: {source}"
        if detail:
            message = f"{message}\n{detail}"
        raise VrewError(message)
    try:
        payload = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VrewError(
            "ffprobe 결과를 UTF-8 JSON으로 읽지 못했습니다. "
            "공식 FFmpeg 배포본인지 확인해 주세요."
        ) from exc
    video = next(
        (stream for stream in payload["streams"] if stream["codec_type"] == "video"),
        None,
    )
    audio = next(
        (stream for stream in payload["streams"] if stream["codec_type"] == "audio"),
        None,
    )
    if not video:
        raise VrewError(f"비디오 스트림이 없습니다: {source}")
    duration = float(
        payload.get("format", {}).get("duration")
        or video.get("duration")
        or 0
    )
    frame_rate_parts = str(video.get("avg_frame_rate", "0/1")).split("/")
    frame_rate = (
        float(frame_rate_parts[0]) / float(frame_rate_parts[1])
        if len(frame_rate_parts) == 2 and float(frame_rate_parts[1])
        else 0
    )
    return {
        "duration": duration,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "frameRate": frame_rate,
        "videoCodec": video.get("codec_name", "unknown"),
        "colorSpace": video.get("color_space") or "bt709",
        "hasAlpha": "a" in str(video.get("pix_fmt", "")),
        "audio": audio,
        "container": Path(source).suffix.lower().lstrip("."),
    }


def _clips_for_duration(
    project: VrewProject, start_clip: int, duration: float
) -> tuple[int, int]:
    end = start_clip
    elapsed = 0.0
    while end < len(project.clips) and elapsed < duration:
        elapsed += clip_duration(project.clips[end])
        end += 1
    return start_clip, end


def attach_video_overlay(
    project: VrewProject,
    video_path: str | Path,
    *,
    start_clip: int = 0,
    end_clip: int | None = None,
    volume: float = 0.5,
    z_index: int = 393,
    loop: bool = False,
) -> dict[str, Any]:
    source = Path(video_path).expanduser().resolve()
    meta = probe_video(source)
    media_id = project.add_media(source)
    project.files.append(
        {
            "version": 1,
            "mediaId": media_id,
            "sourceOrigin": "USER",
            "fileSize": source.stat().st_size,
            "name": source.name,
            "type": "AVMedia",
            "videoAudioMetaInfo": {
                "videoInfo": {
                    "size": {"width": meta["width"], "height": meta["height"]},
                    "frameRate": meta["frameRate"],
                    "codec": meta["videoCodec"],
                    "colorSpace": meta["colorSpace"],
                    "hasAlphaChannel": meta["hasAlpha"],
                },
                **(
                    {
                        "audioInfo": {
                            "sampleRate": int(meta["audio"].get("sample_rate", 0)),
                            "codec": meta["audio"].get("codec_name", "unknown"),
                            "channelCount": int(meta["audio"].get("channels", 0)),
                        }
                    }
                    if meta["audio"]
                    else {}
                ),
                "duration": meta["duration"],
                "presumedDevice": "unknown",
                "mediaContainer": meta["container"],
            },
            "sourceFileType": "ASSET_VIDEO",
            "fileLocation": "LOCAL_TMP",
            "path": str(source),
        }
    )
    video_track = short_id()
    track_ids = [video_track]
    ratio = meta["width"] / meta["height"]
    project_ratio = float(project.data["props"].get("videoRatio", 16 / 9))
    if ratio >= project_ratio:
        width = 1.0
        height = project_ratio / ratio
        x_pos = 0.0
        y_pos = (1 - height) / 2
    else:
        height = 1.0
        width = ratio / project_ratio
        x_pos = (1 - width) / 2
        y_pos = 0.0
    if end_clip is None:
        start, end = _clips_for_duration(project, start_clip, meta["duration"])
        source_out = meta["duration"]
        timeline_duration = sum(
            clip_duration(clip) for clip in project.clips[start:end]
        )
    else:
        start = max(0, start_clip)
        end = min(len(project.clips), end_clip)
        if start >= end:
            raise VrewError(
                f"영상 첨부 클립 범위가 올바르지 않습니다: {start + 1}~{end}"
            )
        timeline_duration = sum(
            clip_duration(clip) for clip in project.clips[start:end]
        )
        # sourceOut is a position in the source media, not the amount of
        # timeline covered. The default is one playback followed by freeze.
        source_out = min(meta["duration"], timeline_duration)

    project.tracks[video_track] = {
        "trackId": video_track,
        "mediaId": media_id,
        "xPos": x_pos,
        "yPos": y_pos,
        "height": height,
        "width": width,
        "rotation": 0,
        "zIndex": z_index,
        "type": "video",
        "sourceIn": 0,
        "sourceOut": source_out,
        "originalWidthHeightRatio": ratio,
        "isTrimmable": True,
        "hasAlphaChannel": meta["hasAlpha"],
        "editInfo": {},
        "endBehavior": "loop" if loop else "freeze",
    }
    if meta["audio"]:
        audio_track = short_id()
        track_ids.append(audio_track)
        project.tracks[audio_track] = {
            "trackId": audio_track,
            "mediaId": media_id,
            "volume": volume,
            "sourceIn": 0,
            "sourceOut": source_out,
            "loop": loop,
            "playbackRate": 1,
            "type": "videoAudio",
        }
    asset_id = uuid_id()
    project.assets[asset_id] = {"trackIds": track_ids, "role": "sub"}
    add_asset_to_clips(project.clips[start:end], asset_id)
    return {
        "assetId": asset_id,
        "startClip": start + 1,
        "endClip": end,
        "sourceDuration": meta["duration"],
        "timelineDuration": timeline_duration,
        "loop": loop,
    }


def discover_intro_videos(directory: str | Path) -> list[Path]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise VrewError(f"인트로 영상 폴더를 찾을 수 없습니다: {root}")
    matches: list[tuple[int, Path]] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() not in {
            ".mp4",
            ".mov",
            ".mkv",
            ".m4v",
        }:
            continue
        match = re.match(r"^intro[\s_-]*(\d+)$", path.stem, re.IGNORECASE)
        if match:
            matches.append((int(match.group(1)), path))
    matches.sort(key=lambda item: (item[0], item[1].name.casefold()))
    return [path for _, path in matches]


def _equal_duration_partitions(
    project: VrewProject, start: int, end: int, count: int
) -> list[tuple[int, int, float]]:
    count = min(count, end - start)
    if count <= 0:
        return []
    durations = [clip_duration(clip) for clip in project.clips[start:end]]
    prefix = [0.0]
    for duration in durations:
        prefix.append(prefix[-1] + duration)
    target = prefix[-1] / count
    size = len(durations)
    infinity = float("inf")
    costs = [[infinity] * (size + 1) for _ in range(count + 1)]
    previous = [[-1] * (size + 1) for _ in range(count + 1)]
    costs[0][0] = 0.0
    for groups in range(1, count + 1):
        for right in range(groups, size + 1):
            for left in range(groups - 1, right):
                if costs[groups - 1][left] == infinity:
                    continue
                duration = prefix[right] - prefix[left]
                score = costs[groups - 1][left] + (duration - target) ** 2
                if score < costs[groups][right]:
                    costs[groups][right] = score
                    previous[groups][right] = left
    boundaries = [size]
    cursor = size
    for groups in range(count, 0, -1):
        cursor = previous[groups][cursor]
        if cursor < 0:
            raise VrewError("인트로 영상 구간을 분할하지 못했습니다.")
        boundaries.append(cursor)
    boundaries.reverse()
    return [
        (
            start + left,
            start + right,
            prefix[right] - prefix[left],
        )
        for left, right in zip(boundaries, boundaries[1:])
    ]


def attach_intro_sequence(
    project: VrewProject,
    directory: str | Path,
    *,
    end_clip: int,
    start_clip: int = 0,
    volume: float = 0.5,
    z_index: int = 1,
) -> dict[str, Any]:
    videos = discover_intro_videos(directory)
    if not videos:
        raise VrewError(f"intro1~n 영상을 찾지 못했습니다: {directory}")
    partitions = _equal_duration_partitions(
        project, start_clip, end_clip, len(videos)
    )
    selected_videos = videos[: len(partitions)]
    placements: list[dict[str, Any]] = []
    for video_path, (start, end, duration) in zip(selected_videos, partitions):
        placement = attach_video_overlay(
            project,
            video_path,
            start_clip=start,
            end_clip=end,
            volume=volume,
            z_index=z_index,
        )
        placement["video"] = str(video_path)
        placement["plannedDuration"] = duration
        placements.append(placement)
    return {
        "directory": str(Path(directory).expanduser().resolve()),
        "discoveredVideoCount": len(videos),
        "attachedVideoCount": len(placements),
        "coveredStartClip": start_clip + 1,
        "coveredEndClip": end_clip,
        "placements": placements,
    }
