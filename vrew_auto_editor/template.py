from __future__ import annotations

import copy
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .project import (
    VrewError,
    VrewProject,
    add_asset_to_clips,
    clip_caption,
    short_id,
    uuid_id,
    validate_integrity,
)


def _normalize(text: str) -> str:
    return "".join(
        char.casefold()
        for char in unicodedata.normalize("NFC", text)
        if char.isalnum()
    )


def _clip_asset_ids(clip: dict[str, Any]) -> set[str]:
    result = set(clip.get("assetIds", []))
    for word in clip.get("words", []):
        result.update(word.get("assetIds", []))
        for truncated in word.get("truncatedWords", []):
            result.update(truncated.get("assetIds", []))
    return result


def _replace_asset_ids(clip: dict[str, Any], mapping: dict[str, str]) -> None:
    clip["assetIds"] = [
        mapping.get(asset_id, asset_id) for asset_id in clip.get("assetIds", [])
    ]
    for word in clip.get("words", []):
        word["id"] = short_id()
        word["assetIds"] = [
            mapping.get(asset_id, asset_id)
            for asset_id in word.get("assetIds", [])
        ]
        for truncated in word.get("truncatedWords", []):
            truncated["id"] = short_id()
            truncated["assetIds"] = [
                mapping.get(asset_id, asset_id)
                for asset_id in truncated.get("assetIds", [])
            ]


def _unique_media_id(target: VrewProject, preferred: str) -> str:
    existing = {str(item.get("mediaId")) for item in target.files}
    return preferred if preferred not in existing else uuid_id()


@dataclass
class ImportedTemplate:
    clips: list[dict[str, Any]]
    asset_ids: dict[str, str]
    track_ids: dict[str, str]
    media_ids: dict[str, str]


def import_template_clips(
    target: VrewProject,
    source_path: str | Path,
    *,
    start: int = 0,
    end: int | None = None,
    scene_id: str | None = None,
) -> ImportedTemplate:
    source = VrewProject.load(source_path)
    end = len(source.clips) if end is None else end
    if start < 0 or end > len(source.clips) or start >= end:
        raise VrewError(
            f"공통 클립 범위가 올바르지 않습니다: {start + 1}~{end}"
        )
    clips = copy.deepcopy(source.clips[start:end])
    old_asset_ids = set().union(*(_clip_asset_ids(clip) for clip in clips))
    missing_assets = old_asset_ids - set(source.assets)
    if missing_assets:
        raise VrewError(
            "공통 파일에 누락된 asset이 있습니다: "
            + ", ".join(sorted(missing_assets))
        )

    asset_mapping = {asset_id: uuid_id() for asset_id in old_asset_ids}
    old_track_ids = {
        track_id
        for asset_id in old_asset_ids
        for track_id in source.assets[asset_id].get("trackIds", [])
    }
    missing_tracks = old_track_ids - set(source.tracks)
    if missing_tracks:
        raise VrewError(
            "공통 파일에 누락된 track이 있습니다: "
            + ", ".join(sorted(missing_tracks))
        )
    track_mapping = {track_id: short_id() for track_id in old_track_ids}

    old_media_ids = {
        str(source.tracks[track_id].get("mediaId"))
        for track_id in old_track_ids
        if source.tracks[track_id].get("mediaId")
    }
    source_files = {
        str(item.get("mediaId")): item
        for item in source.files
        if item.get("mediaId") is not None
    }
    target_files = {
        str(item.get("mediaId")): item
        for item in target.files
        if item.get("mediaId") is not None
    }
    media_mapping: dict[str, str] = {}

    with zipfile.ZipFile(source.source_path) as archive:
        archive_names = archive.namelist()
        for old_media_id in old_media_ids:
            if old_media_id in target_files:
                media_mapping[old_media_id] = old_media_id
                continue
            file_info = source_files.get(old_media_id)
            if file_info is None:
                # Built-in Vrew resource without an embedded file entry.
                media_mapping[old_media_id] = old_media_id
                continue
            new_media_id = _unique_media_id(target, old_media_id)
            media_mapping[old_media_id] = new_media_id
            new_file_info = copy.deepcopy(file_info)
            new_file_info["mediaId"] = new_media_id
            new_file_info.pop("path", None)
            target.files.append(new_file_info)

            members = [
                name
                for name in archive_names
                if name.startswith(f"media/{old_media_id}.")
            ]
            for member in members:
                suffix = member[len(f"media/{old_media_id}") :]
                target.add_embedded_media(
                    f"media/{new_media_id}{suffix}", archive.read(member)
                )

    for old_track_id in old_track_ids:
        new_track_id = track_mapping[old_track_id]
        track = copy.deepcopy(source.tracks[old_track_id])
        track["trackId"] = new_track_id
        if track.get("mediaId") in media_mapping:
            track["mediaId"] = media_mapping[str(track["mediaId"])]
        target.tracks[new_track_id] = track

    for old_asset_id in old_asset_ids:
        new_asset_id = asset_mapping[old_asset_id]
        asset = copy.deepcopy(source.assets[old_asset_id])
        asset["trackIds"] = [
            track_mapping[track_id] for track_id in asset.get("trackIds", [])
        ]
        target.assets[new_asset_id] = asset

    new_scene_id = scene_id or short_id()
    for clip in clips:
        clip["id"] = short_id()
        clip["sceneId"] = new_scene_id
        _replace_asset_ids(clip, asset_mapping)

    return ImportedTemplate(clips, asset_mapping, track_mapping, media_mapping)


def _find_prefix(
    clips: list[dict[str, Any]], prefix: str, *, start: int = 0
) -> int:
    normalized_prefix = _normalize(prefix)
    for index in range(start, len(clips)):
        if _normalize(clip_caption(clips[index])).startswith(normalized_prefix):
            return index
    raise VrewError(f"클립 시작 문구를 찾지 못했습니다: {prefix}")


def _remove_orphaned_assets(
    project: VrewProject, candidate_asset_ids: Iterable[str]
) -> None:
    used_asset_ids = set().union(*(_clip_asset_ids(clip) for clip in project.clips))
    for asset_id in candidate_asset_ids:
        if asset_id in used_asset_ids:
            continue
        asset = project.assets.pop(asset_id, None)
        if not asset:
            continue
        for track_id in asset.get("trackIds", []):
            used_elsewhere = any(
                track_id in other.get("trackIds", [])
                for other in project.assets.values()
            )
            if not used_elsewhere:
                project.tracks.pop(track_id, None)


def _caption_attributes(caption: dict[str, Any]) -> dict[str, Any]:
    for operation in caption.get("text", []):
        attributes = operation.get("attributes")
        if attributes:
            return copy.deepcopy(attributes)
    return {}


def _caption_template_summary(template: VrewProject) -> dict[str, Any]:
    if not template.clips or not template.clips[0].get("captions"):
        raise VrewError("공통 파일 첫 클립에 자막 서식이 없습니다.")
    primary_caption = template.clips[0]["captions"][0]
    attributes = _caption_attributes(primary_caption)
    style = primary_caption.get("style", {})
    return {
        "templateClip": 1,
        "font": attributes.get("font"),
        "fontSize": attributes.get("size"),
        "color": attributes.get("color"),
        "outlineColor": attributes.get("outline-color"),
        "outlineWidth": attributes.get("outline-width"),
        "position": {
            key: style.get(key)
            for key in (
                "yAlign",
                "yOffset",
                "xOffset",
                "rotation",
                "width",
                "scaleFactor",
            )
        },
    }


def apply_caption_template_style(
    project: VrewProject, template: VrewProject
) -> dict[str, Any]:
    if not template.clips or not template.clips[0].get("captions"):
        raise VrewError("공통 파일 첫 클립에 자막 서식이 없습니다.")

    template_captions = template.clips[0]["captions"]
    styled_caption_count = 0
    styled_operation_count = 0
    for clip in project.clips:
        for index, caption in enumerate(clip.get("captions", [])):
            source_caption = template_captions[
                min(index, len(template_captions) - 1)
            ]
            if "style" in source_caption:
                caption["style"] = copy.deepcopy(source_caption["style"])
            attributes = _caption_attributes(source_caption)
            for operation in caption.get("text", []):
                if not isinstance(operation.get("insert"), str):
                    continue
                if attributes:
                    operation["attributes"] = copy.deepcopy(attributes)
                else:
                    operation.pop("attributes", None)
                styled_operation_count += 1
            styled_caption_count += 1

    source_global_style = template.data.get("props", {}).get(
        "globalCaptionStyle"
    )
    if source_global_style is not None:
        project.data["props"]["globalCaptionStyle"] = copy.deepcopy(
            source_global_style
        )
    if "captionDisplayMode" in template.data.get("props", {}):
        project.data["props"]["captionDisplayMode"] = copy.deepcopy(
            template.data["props"]["captionDisplayMode"]
        )

    return {
        **_caption_template_summary(template),
        "styledClipCount": len(project.clips),
        "styledCaptionCount": styled_caption_count,
        "styledTextOperationCount": styled_operation_count,
    }


def apply_common_template(
    project: VrewProject,
    source_path: str | Path,
    *,
    subscribe_prefix: str = "구독과 좋아요는",
    story_prefix: str = "옛날 옛적",
) -> dict[str, Any]:
    source = VrewProject.load(source_path)
    if len(source.clips) < 7:
        raise VrewError(
            f"공통 파일에는 최소 7개 클립이 필요합니다: {len(source.clips)}개"
        )
    subscribe_index = _find_prefix(project.clips, subscribe_prefix)
    story_index = _find_prefix(
        project.clips, story_prefix, start=subscribe_index + 1
    )
    target_scene_id = project.clips[subscribe_index].get("sceneId")
    imported = import_template_clips(
        project,
        source_path,
        start=0,
        end=7,
        scene_id=target_scene_id,
    )
    removed = project.clips[subscribe_index:story_index]
    removed_asset_ids = set().union(*(_clip_asset_ids(clip) for clip in removed))
    project.data["transcript"]["clips"][subscribe_index:story_index] = (
        imported.clips[:2]
    )
    _remove_orphaned_assets(project, removed_asset_ids)

    outro_start = len(project.clips)
    project.data["transcript"]["clips"].extend(imported.clips[2:7])

    first_two_assets = set().union(
        *(_clip_asset_ids(clip) for clip in imported.clips[:2])
    )
    global_asset_ids: list[str] = []
    for asset_id in first_two_assets:
        track_types = {
            project.tracks[track_id].get("type")
            for track_id in project.assets[asset_id].get("trackIds", [])
        }
        if track_types <= {"image", "web"}:
            global_asset_ids.append(asset_id)

    # Bring the common watermark and AI notice above all other visual tracks,
    # then reuse the exact template assets across the complete target project.
    current_max_z = max(
        (
            int(track.get("zIndex", 0) or 0)
            for track in project.tracks.values()
            if track.get("type") in {"image", "video", "web"}
        ),
        default=0,
    )
    for offset, asset_id in enumerate(
        sorted(
            global_asset_ids,
            key=lambda value: min(
                int(project.tracks[track_id].get("zIndex", 0) or 0)
                for track_id in project.assets[value]["trackIds"]
            ),
        ),
        start=1,
    ):
        for track_id in project.assets[asset_id]["trackIds"]:
            project.tracks[track_id]["zIndex"] = current_max_z + offset
        add_asset_to_clips(project.clips, asset_id)

    caption_style_report = apply_caption_template_style(project, source)

    return {
        "source": str(Path(source_path).expanduser().resolve()),
        "subscribeStartClip": subscribe_index + 1,
        "removedStartClip": subscribe_index + 1,
        "removedEndClip": story_index,
        "removedClipCount": len(removed),
        "insertedSubscribeClipCount": 2,
        "storyStartClip": subscribe_index + 3,
        "outroStartClip": outro_start + 1,
        "insertedOutroClipCount": 5,
        "globalAssetIds": global_asset_ids,
        "globalizedClipCount": len(project.clips),
        "captionStyle": caption_style_report,
        "removedCaptions": [clip_caption(clip) for clip in removed],
        "subscribeCaptions": [
            clip_caption(clip) for clip in imported.clips[:2]
        ],
        "outroCaptions": [clip_caption(clip) for clip in imported.clips[2:7]],
    }


def analyze_common_template(
    target: VrewProject, source_path: str | Path
) -> dict[str, Any]:
    source = VrewProject.load(source_path)
    subscribe_index = _find_prefix(target.clips, "구독과 좋아요는")
    story_index = _find_prefix(
        target.clips, "옛날 옛적", start=subscribe_index + 1
    )
    return {
        "source": str(source.source_path),
        "integrityValid": validate_integrity(source.data),
        "clipCount": len(source.clips),
        "usable": len(source.clips) >= 7,
        "targetSubscribeStartClip": subscribe_index + 1,
        "targetStoryStartClip": story_index + 1,
        "targetReplacementClipCount": story_index - subscribe_index,
        "captionStyle": _caption_template_summary(source),
        "subscribeCaptions": [
            clip_caption(clip) for clip in source.clips[:2]
        ],
        "outroCaptions": [clip_caption(clip) for clip in source.clips[2:7]],
    }
