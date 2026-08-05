from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vrew_auto_editor.discovery import discover_companion_paths


class CompanionDiscoveryTests(unittest.TestCase):
    def test_discovers_script_nested_images_intros_and_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "영상08.vrew"
            source.touch()
            script = root / "story_flow_prompts.txt"
            script.write_text("1. 첫 대사\n2. 둘째 대사\n3) 셋째 대사\n", encoding="utf-8")
            nested = root / "images" / "selected"
            nested.mkdir(parents=True)
            (nested / "001-1.jpeg").touch()
            (nested / "002-1.png").touch()
            (root / "intro2.mp4").touch()
            (root / "intro1.mp4").touch()

            result = discover_companion_paths(source)

        self.assertEqual(Path(result["script"]), script.resolve())
        self.assertEqual(result["scriptLineCount"], 3)
        self.assertEqual(Path(result["images"]), nested.resolve())
        self.assertEqual(result["numberedImageCount"], 2)
        self.assertEqual(
            [Path(path).name for path in result["introVideos"]],
            ["intro1.mp4", "intro2.mp4"],
        )
        self.assertEqual(
            Path(result["output"]).name,
            "영상08_작업완료.vrew",
        )
        self.assertIsNone(result["sourceMeta"])

    def test_image_root_does_not_depend_on_fixed_folder_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.vrew"
            source.touch()
            arbitrary = root / "아무폴더" / "컷"
            arbitrary.mkdir(parents=True)
            (arbitrary / "001.jpeg").touch()
            (arbitrary / "002.jpeg").touch()

            result = discover_companion_paths(source)

        self.assertEqual(Path(result["images"]), arbitrary.resolve())
        self.assertEqual(result["numberedImageCount"], 2)

    def test_numeric_intro_names_are_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.vrew"
            source.touch()
            (root / "1.mp4").touch()
            (root / "02.mp4").touch()
            (root / "intro 3.mp4").touch()
            (root / "clip.mp4").touch()

            result = discover_companion_paths(source)

        self.assertEqual(
            [Path(path).name for path in result["introVideos"]],
            ["1.mp4", "02.mp4", "intro 3.mp4"],
        )

    def test_missing_optional_files_are_reported_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.vrew"
            source.touch()
            result = discover_companion_paths(source)

        self.assertIsNone(result["script"])
        self.assertIsNone(result["scriptLineCount"])
        self.assertIsNone(result["images"])
        self.assertIsNone(result["introDirectory"])
        self.assertEqual(len(result["warnings"]), 3)


if __name__ == "__main__":
    unittest.main()
