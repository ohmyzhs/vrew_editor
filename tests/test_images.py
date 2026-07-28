from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from vrew_auto_editor.images import (
    attach_numbered_images,
    match_script_to_clips,
    parse_numbered_script,
    partition_clip_range,
)
from vrew_auto_editor.project import VrewProject


def clip(caption: str, duration: float) -> dict:
    return {
        "captions": [{"text": [{"insert": caption + "\n"}]}],
        "words": [{"duration": duration}],
    }


class ImagePlanningTests(unittest.TestCase):
    def test_numbered_script_uses_first_duplicate(self) -> None:
        parsed = parse_numbered_script("1. 첫 문장\n2) 둘째\n1. 다른 문장")
        self.assertEqual(parsed, {1: "첫 문장", 2: "둘째"})

    def test_script_can_span_multiple_clips(self) -> None:
        clips = [clip("옛날 옛적 강원도", 3), clip("두메산골에 살았습니다.", 3)]
        matches, unmatched = match_script_to_clips(
            clips, {1: "옛날 옛적 강원도 두메산골에 살았습니다."}
        )
        self.assertFalse(unmatched)
        self.assertEqual(matches[0].clip_index, 0)

    def test_partition_balances_tail(self) -> None:
        clips = [clip(str(index), 2.5) for index in range(28)]
        segments = partition_clip_range(clips, 0, len(clips), 15, 20)
        self.assertEqual(sum(end - start for start, end, _ in segments), len(clips))
        self.assertTrue(all(15 <= duration <= 20 for _, _, duration in segments))

    def test_disabled_ken_burns_uses_one_asset_for_full_number_range(self) -> None:
        project = VrewProject(
            Path("dummy.vrew"),
            {
                "transcript": {
                    "clips": [
                        {**clip("첫 장면", 10), "assetIds": []},
                        {**clip("이어지는 장면", 10), "assetIds": []},
                        {**clip("마지막 장면", 10), "assetIds": []},
                    ]
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
            image = Path(directory) / "001.png"
            image.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + b"\x00" * 8
                + (1920).to_bytes(4, "big")
                + (1080).to_bytes(4, "big")
                + b"\x08\x02"
            )
            report = attach_numbered_images(
                project,
                {1: "첫 장면"},
                {1: image},
                ken_burns=False,
            )

        self.assertFalse(report["kenBurnsEnabled"])
        self.assertEqual(report["segmentCount"], 1)
        self.assertEqual(report["batchAnimationCount"], 0)
        asset_id = report["placements"][0]["segments"][0]["assetId"]
        self.assertTrue(all(asset_id in item["assetIds"] for item in project.clips))
        track_id = project.assets[asset_id]["trackIds"][0]
        self.assertNotIn("kenburnsAnimationInfo", project.tracks[track_id])


if __name__ == "__main__":
    unittest.main()
