from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vrew_auto_editor.gui import HTML
from vrew_auto_editor.postprocess import (
    _equal_duration_partitions,
    attach_video_overlay,
    discover_intro_videos,
)
from vrew_auto_editor.project import VrewProject


def clip(duration: float) -> dict:
    return {"words": [{"duration": duration}], "captions": [], "assetIds": []}


class IntroPlanningTests(unittest.TestCase):
    def test_intro_files_are_numerically_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("intro10.mp4", "intro2.mp4", "intro1.mp4", "other.mp4"):
                (root / name).touch()
            self.assertEqual(
                [path.name for path in discover_intro_videos(root)],
                ["intro1.mp4", "intro2.mp4", "intro10.mp4"],
            )

    def test_partitions_cover_range_without_gaps(self) -> None:
        project = VrewProject(
            Path("dummy.vrew"),
            {
                "transcript": {"clips": [clip(value) for value in (3, 5, 2, 7, 4)]},
                "props": {"tracks": {}, "assets": {}},
                "files": [],
            },
        )
        partitions = _equal_duration_partitions(project, 0, 5, 3)
        self.assertEqual(partitions[0][0], 0)
        self.assertEqual(partitions[-1][1], 5)
        self.assertTrue(
            all(left[1] == right[0] for left, right in zip(partitions, partitions[1:]))
        )

    @patch("vrew_auto_editor.postprocess.probe_video")
    def test_intro_video_defaults_to_single_playback(self, probe) -> None:
        probe.return_value = {
            "duration": 2.0,
            "width": 1920,
            "height": 1080,
            "frameRate": 30.0,
            "videoCodec": "h264",
            "colorSpace": "bt709",
            "hasAlpha": False,
            "audio": {
                "sample_rate": "48000",
                "codec_name": "aac",
                "channels": 2,
            },
            "container": "mp4",
        }
        project = VrewProject(
            Path("dummy.vrew"),
            {
                "transcript": {
                    "clips": [clip(3.0), clip(3.0)]
                },
                "props": {
                    "tracks": {},
                    "assets": {},
                    "videoRatio": 16 / 9,
                },
                "files": [],
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "intro1.mp4"
            video.touch()
            report = attach_video_overlay(
                project,
                video,
                start_clip=0,
                end_clip=2,
            )

        track_ids = project.assets[report["assetId"]]["trackIds"]
        video_track = next(
            project.tracks[track_id]
            for track_id in track_ids
            if project.tracks[track_id]["type"] == "video"
        )
        audio_track = next(
            project.tracks[track_id]
            for track_id in track_ids
            if project.tracks[track_id]["type"] == "videoAudio"
        )
        self.assertEqual(video_track["endBehavior"], "freeze")
        self.assertFalse(audio_track["loop"])
        self.assertFalse(report["loop"])


class GuiTests(unittest.TestCase):
    def test_all_path_fields_have_native_picker_buttons(self) -> None:
        for target in (
            "source",
            "script",
            "images",
            "commonTemplate",
            "introDirectory",
            "output",
        ):
            self.assertIn(f'data-target="{target}"', HTML)


if __name__ == "__main__":
    unittest.main()
