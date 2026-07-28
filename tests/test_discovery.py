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
            script.touch()
            studio = root / "Flow Batch Studio"
            nested = studio / "selected"
            nested.mkdir(parents=True)
            (nested / "001-1.jpeg").touch()
            (nested / "002-1.png").touch()
            (root / "intro2.mp4").touch()
            (root / "intro1.mp4").touch()

            result = discover_companion_paths(source)

        self.assertEqual(Path(result["script"]), script.resolve())
        self.assertEqual(Path(result["images"]), studio.resolve())
        self.assertEqual(result["numberedImageCount"], 2)
        self.assertEqual(
            [Path(path).name for path in result["introVideos"]],
            ["intro1.mp4", "intro2.mp4"],
        )
        self.assertEqual(
            Path(result["output"]).name,
            "영상08_작업완료.vrew",
        )

    def test_missing_optional_files_are_reported_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.vrew"
            source.touch()
            result = discover_companion_paths(source)

        self.assertIsNone(result["script"])
        self.assertIsNone(result["images"])
        self.assertIsNone(result["introDirectory"])
        self.assertEqual(len(result["warnings"]), 3)


if __name__ == "__main__":
    unittest.main()
