from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .clips import repair_dialogue_clips
from .images import (
    attach_numbered_images,
    discover_numbered_images,
    match_script_to_clips,
    parse_numbered_script,
)
from .postprocess import (
    attach_ai_notice,
    attach_global_watermark,
    attach_intro_sequence,
    attach_video_overlay,
)
from .project import VrewError, VrewProject, clip_duration, uuid_id, validate_integrity
from .template import (
    analyze_common_template,
    apply_common_template,
    apply_final_caption_style,
)


def _load_script(script: str | Path | None) -> tuple[str, dict[int, str]]:
    if script is None:
        return "", {}
    script_text: str
    candidate = Path(str(script)).expanduser()
    if "\n" not in str(script) and candidate.is_file():
        script_text = candidate.read_text(encoding="utf-8")
    else:
        script_text = str(script)
    return script_text, parse_numbered_script(script_text)


def analyze_project(
    source_path: str | Path,
    *,
    script: str | Path | None = None,
    image_directory: str | Path | None = None,
    preferred_variant: str = "1",
    max_chars: int = 20,
    common_template: str | Path | None = None,
) -> dict[str, Any]:
    project = VrewProject.load(source_path)
    repaired_clips, repair_report = repair_dialogue_clips(
        copy.deepcopy(project.clips), max_chars
    )
    _, numbered_script = _load_script(script)
    selected_images: dict[int, Path] = {}
    conflicts: dict[int, list[Path]] = {}
    if image_directory:
        selected_images, conflicts = discover_numbered_images(
            image_directory, preferred_variant
        )
    matches, unmatched = (
        match_script_to_clips(repaired_clips, numbered_script)
        if numbered_script
        else ([], [])
    )
    report = {
        "source": str(project.source_path),
        "projectVersion": project.data.get("version"),
        "integrityValid": validate_integrity(project.data),
        "clipCount": len(project.clips),
        "durationSeconds": round(sum(clip_duration(c) for c in project.clips), 3),
        "ttsMediaCount": len(project.data["props"].get("ttsClipInfosMap", {})),
        "clipRepair": repair_report.to_dict(),
        "scriptLineCount": len(numbered_script),
        "matchedScriptCount": len(matches),
        "unmatchedScript": unmatched,
        "discoveredImageCount": len(selected_images),
        "missingImageNumbers": sorted(set(numbered_script) - set(selected_images)),
        "imageConflicts": {
            str(number): [str(path) for path in paths]
            for number, paths in conflicts.items()
        },
        "selectedImages": {
            str(number): str(path) for number, path in selected_images.items()
        },
    }
    if common_template:
        preview_project = VrewProject(
            project.source_path,
            copy.deepcopy(project.data),
        )
        preview_project.data["transcript"]["clips"] = repaired_clips
        report["commonTemplate"] = analyze_common_template(
            preview_project, common_template
        )
    return report


def transform_project(
    source_path: str | Path,
    output_path: str | Path,
    *,
    script: str | Path | None = None,
    image_directory: str | Path | None = None,
    preferred_variant: str = "1",
    repair_clips: bool = True,
    attach_images: bool = True,
    max_chars: int = 20,
    seed: int = 20260728,
    minimum_seconds: float = 15.0,
    maximum_seconds: float = 20.0,
    ken_burns: bool = True,
    common_template: str | Path | None = None,
    intro_directory: str | Path | None = None,
    intro_video: str | Path | None = None,
    subscribe_video: str | Path | None = None,
    subscribe_start_clip: int | None = None,
    outro_video: str | Path | None = None,
    watermark: str | Path | None = None,
    ai_notice: str | None = None,
) -> dict[str, Any]:
    project = VrewProject.load(source_path)
    report: dict[str, Any] = {
        "source": str(project.source_path),
        "inputIntegrityValid": validate_integrity(project.data),
        "sourceProjectId": project.data.get("projectId"),
    }
    project.data["projectId"] = uuid_id()
    report["outputProjectId"] = project.data["projectId"]

    if repair_clips:
        repaired, clip_report = repair_dialogue_clips(project.clips, max_chars)
        project.data["transcript"]["clips"] = repaired
        report["clipRepair"] = clip_report.to_dict()

    common_report: dict[str, Any] | None = None
    if common_template:
        common_report = apply_common_template(project, common_template)
        report["commonTemplate"] = common_report

    if intro_directory:
        if not common_report:
            raise VrewError(
                "인트로 자동 분배에는 구독 시작점을 제공하는 공통 Vrew 파일이 필요합니다."
            )
        report["introSequence"] = attach_intro_sequence(
            project,
            intro_directory,
            end_clip=common_report["subscribeStartClip"] - 1,
        )

    _, numbered_script = _load_script(script)
    if attach_images:
        if not numbered_script:
            raise VrewError("이미지 첨부에는 넘버링된 대본이 필요합니다.")
        if not image_directory:
            raise VrewError("이미지 첨부에는 이미지 폴더가 필요합니다.")
        image_paths, conflicts = discover_numbered_images(
            image_directory, preferred_variant
        )
        report["images"] = attach_numbered_images(
            project,
            numbered_script,
            image_paths,
            seed=seed,
            minimum_seconds=minimum_seconds,
            maximum_seconds=maximum_seconds,
            ken_burns=ken_burns,
            coverage_end_clip=(
                common_report["outroStartClip"] - 1 if common_report else None
            ),
        )
        report["images"]["conflicts"] = {
            str(number): [str(path) for path in paths]
            for number, paths in conflicts.items()
        }

    if intro_video:
        report["introVideo"] = attach_video_overlay(project, intro_video, start_clip=0)
    if subscribe_video:
        if subscribe_start_clip is None:
            raise VrewError("구독 영상에는 시작 클립 번호가 필요합니다.")
        report["subscribeVideo"] = attach_video_overlay(
            project, subscribe_video, start_clip=max(0, subscribe_start_clip - 1)
        )
    if outro_video:
        from .postprocess import probe_video

        duration = probe_video(outro_video)["duration"]
        cursor = len(project.clips)
        elapsed = 0.0
        while cursor > 0 and elapsed < duration:
            cursor -= 1
            elapsed += clip_duration(project.clips[cursor])
        report["outroVideo"] = attach_video_overlay(
            project, outro_video, start_clip=cursor
        )
    if watermark:
        report["watermarkAssetId"] = attach_global_watermark(project, watermark)
    if ai_notice is not None:
        report["aiNoticeAssetId"] = attach_ai_notice(
            project, ai_notice or "이 영상은 AI기술을 이용한 창작물입니다."
        )

    report["finalCaptionStyle"] = apply_final_caption_style(project)

    output = project.save(output_path)
    reloaded = VrewProject.load(output)
    report["output"] = str(output)
    report["outputIntegrityValid"] = validate_integrity(reloaded.data)
    report["finalClipCount"] = len(reloaded.clips)
    report["finalTrackCount"] = len(reloaded.tracks)
    report["finalAssetCount"] = len(reloaded.assets)
    return report


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output
