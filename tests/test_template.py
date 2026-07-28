from __future__ import annotations

import unittest
import json
import tempfile
import zipfile
from pathlib import Path

from vrew_auto_editor.template import (
    apply_caption_template_style,
    import_template_clips,
)
from vrew_auto_editor.project import VrewProject


def project(captions: list[dict], global_style: dict | None = None) -> VrewProject:
    return VrewProject(
        Path("dummy.vrew"),
        {
            "transcript": {
                "clips": [
                    {
                        "captions": captions,
                        "words": [],
                        "assetIds": [],
                    }
                ]
            },
            "props": {
                "tracks": {},
                "assets": {},
                "globalCaptionStyle": global_style or {},
            },
            "files": [],
        },
    )


class CaptionTemplateTests(unittest.TestCase):
    def test_copies_font_and_position_without_changing_text(self) -> None:
        target = project(
            [{"text": [{"insert": "원래 자막\n"}]}, {"text": [{"insert": "\n"}]}]
        )
        template = project(
            [
                {
                    "text": [
                        {
                            "insert": "서식 원본",
                            "attributes": {
                                "font": "BM EULJIRO-Vrew_400",
                                "size": "180",
                                "color": "#eaf28f",
                            },
                        }
                    ],
                    "style": {"yAlign": "bottom", "yOffset": -0.1125},
                },
                {
                    "text": [
                        {
                            "insert": "\n",
                            "attributes": {"font": "BM EULJIRO-Vrew_400"},
                        }
                    ],
                    "style": {"yAlign": "bottom", "yOffset": -0.1125},
                },
            ],
            {"quillStyle": {"font": "Template Global"}},
        )

        report = apply_caption_template_style(target, template)

        self.assertEqual(target.clips[0]["captions"][0]["text"][0]["insert"], "원래 자막\n")
        self.assertEqual(
            target.clips[0]["captions"][0]["text"][0]["attributes"]["font"],
            "BM EULJIRO-Vrew_400",
        )
        self.assertEqual(
            target.clips[0]["captions"][0]["style"]["yOffset"], -0.1125
        )
        self.assertEqual(
            target.data["props"]["globalCaptionStyle"]["quillStyle"]["font"],
            "Template Global",
        )
        self.assertEqual(report["styledClipCount"], 1)

    def test_imported_clips_can_reuse_target_scene_id(self) -> None:
        source_data = {
            "version": 17,
            "transcript": {
                "clips": [
                    {
                        "id": "source-clip",
                        "sceneId": "source-scene",
                        "words": [],
                        "captions": [],
                        "assetIds": [],
                    }
                ]
            },
            "props": {"tracks": {}, "assets": {}},
            "files": [],
        }
        target = VrewProject(
            Path("target.vrew"),
            {
                "transcript": {"clips": []},
                "props": {"tracks": {}, "assets": {}},
                "files": [],
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "template.vrew"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "project.json",
                    json.dumps(source_data, ensure_ascii=False),
                )
            imported = import_template_clips(
                target,
                source,
                start=0,
                end=1,
                scene_id="target-scene",
            )

        self.assertEqual(imported.clips[0]["sceneId"], "target-scene")


if __name__ == "__main__":
    unittest.main()
