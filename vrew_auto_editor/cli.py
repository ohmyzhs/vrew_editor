from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .discovery import discover_companion_paths
from .project import VrewError
from .workflow import analyze_project, transform_project, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vrew-auto",
        description="Vrew 프로젝트 클립/이미지/후처리 자동화",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser(
        "discover",
        help="원본 Vrew 주변의 대본·이미지·인트로와 기본 출력 경로 탐색",
    )
    discover.add_argument("source")

    analyze = subparsers.add_parser("analyze", help="원본을 변경하지 않고 분석")
    analyze.add_argument("source")
    analyze.add_argument("--script")
    analyze.add_argument("--images")
    analyze.add_argument("--variant", default="1")
    analyze.add_argument("--max-chars", type=int, default=20)
    analyze.add_argument("--common-template")
    analyze.add_argument("--report")

    transform = subparsers.add_parser("transform", help="복제본 Vrew 생성")
    transform.add_argument("source")
    transform.add_argument("output")
    transform.add_argument("--script")
    transform.add_argument("--images")
    transform.add_argument("--variant", default="1")
    transform.add_argument("--max-chars", type=int, default=20)
    transform.add_argument("--seed", type=int, default=20260728)
    transform.add_argument("--min-seconds", type=float, default=15.0)
    transform.add_argument("--max-seconds", type=float, default=20.0)
    transform.add_argument("--common-template")
    transform.add_argument("--intro-directory")
    transform.add_argument("--no-repair", action="store_true")
    transform.add_argument("--no-images", action="store_true")
    transform.add_argument(
        "--no-ken-burns",
        action="store_true",
        help="이미지를 번호별 전체 구간에 한 번만 배치하고 움직임 효과를 생략",
    )
    transform.add_argument("--intro-video")
    transform.add_argument("--subscribe-video")
    transform.add_argument("--subscribe-start-clip", type=int)
    transform.add_argument("--outro-video")
    transform.add_argument("--watermark")
    transform.add_argument(
        "--ai-notice",
        nargs="?",
        const="이 영상은 AI기술을 이용한 창작물입니다.",
    )
    transform.add_argument("--report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover":
            report = discover_companion_paths(args.source)
        elif args.command == "analyze":
            report = analyze_project(
                args.source,
                script=args.script,
                image_directory=args.images,
                preferred_variant=args.variant,
                max_chars=args.max_chars,
                common_template=args.common_template,
            )
        else:
            report = transform_project(
                args.source,
                args.output,
                script=args.script,
                image_directory=args.images,
                preferred_variant=args.variant,
                repair_clips=not args.no_repair,
                attach_images=not args.no_images,
                max_chars=args.max_chars,
                seed=args.seed,
                minimum_seconds=args.min_seconds,
                maximum_seconds=args.max_seconds,
                ken_burns=not args.no_ken_burns,
                common_template=args.common_template,
                intro_directory=args.intro_directory,
                intro_video=args.intro_video,
                subscribe_video=args.subscribe_video,
                subscribe_start_clip=args.subscribe_start_clip,
                outro_video=args.outro_video,
                watermark=args.watermark,
                ai_notice=args.ai_notice,
            )
        report_path = getattr(args, "report", None)
        if report_path:
            write_report(report, report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (VrewError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
