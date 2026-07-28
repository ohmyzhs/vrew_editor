from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .images import IMAGE_SUFFIXES
from .postprocess import discover_intro_videos
from .project import VrewError


NUMBERED_IMAGE = re.compile(r"^\d{1,4}(?:[-_]\d+)?(?:\D|$)")


def _numbered_image_paths(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and NUMBERED_IMAGE.match(path.stem)
        ),
        key=lambda path: str(path).casefold(),
    )


def _preferred_image_root(base: Path, images: list[Path]) -> Path | None:
    if not images:
        return None

    studio_roots: Counter[Path] = Counter()
    for image in images:
        for parent in image.parents:
            if parent == base.parent:
                break
            if parent.name.casefold() == "flow batch studio":
                studio_roots[parent] += 1
                break
            if parent == base:
                break
    if studio_roots:
        return sorted(
            studio_roots,
            key=lambda path: (-studio_roots[path], str(path).casefold()),
        )[0]

    common = Path(os.path.commonpath([str(path.parent) for path in images]))
    return common if common == base or base in common.parents else base


def discover_companion_paths(source_path: str | Path) -> dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise VrewError(f"Vrew 원본을 찾을 수 없습니다: {source}")
    if source.suffix.lower() != ".vrew":
        raise VrewError(f"Vrew 원본만 선택할 수 있습니다: {source.name}")

    base = source.parent
    scripts = sorted(
        base.glob("*_flow_prompts.txt"),
        key=lambda path: path.name.casefold(),
    )
    numbered_images = _numbered_image_paths(base)
    image_root = _preferred_image_root(base, numbered_images)
    intros = discover_intro_videos(base)
    output = source.with_name(f"{source.stem}_작업완료.vrew")

    warnings: list[str] = []
    if not scripts:
        warnings.append("*_flow_prompts.txt를 찾지 못했습니다.")
    elif len(scripts) > 1:
        warnings.append(
            f"넘버링 대본이 {len(scripts)}개라 이름순 첫 파일을 선택했습니다."
        )
    if not numbered_images:
        warnings.append("하위 폴더에서 번호 이미지를 찾지 못했습니다.")
    if not intros:
        warnings.append("원본 폴더에서 intro1~n 영상을 찾지 못했습니다.")

    return {
        "source": str(source),
        "directory": str(base),
        "script": str(scripts[0]) if scripts else None,
        "scriptCandidates": [str(path) for path in scripts],
        "images": str(image_root) if image_root else None,
        "numberedImageCount": len(numbered_images),
        "introDirectory": str(base) if intros else None,
        "introVideos": [str(path) for path in intros],
        "output": str(output),
        "warnings": warnings,
    }
