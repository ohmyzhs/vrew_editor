from __future__ import annotations

import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vrew_auto_editor.project import compute_integrity, validate_integrity
from vrew_auto_editor.workflow import transform_project


class IntegrityTests(unittest.TestCase):
    def test_paths_are_excluded_and_integrity_is_blank(self) -> None:
        project = {
            "version": 17,
            "files": [{"mediaId": "m1", "path": "/tmp/a.mp4"}],
            "integrity": "old",
            "transcript": {"clips": []},
            "props": {"tracks": {}, "assets": {}},
        }
        without_other_path = copy.deepcopy(project)
        without_other_path["files"][0]["path"] = "C:\\Temp\\a.mp4"
        self.assertEqual(compute_integrity(project), compute_integrity(without_other_path))

        project["integrity"] = compute_integrity(project)
        self.assertTrue(validate_integrity(project))
        project["version"] = 16
        self.assertFalse(validate_integrity(project))

    def test_transform_assigns_a_new_project_identity(self) -> None:
        source_data = {
            "version": 17,
            "projectId": "source-project",
            "integrity": "",
            "transcript": {"clips": []},
            "props": {"tracks": {}, "assets": {}},
            "files": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.vrew"
            output = Path(directory) / "output.vrew"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("project.json", json.dumps(source_data))
            report = transform_project(
                source,
                output,
                repair_clips=False,
                attach_images=False,
            )
            with zipfile.ZipFile(output) as archive:
                output_data = json.loads(archive.read("project.json"))

        self.assertEqual(report["sourceProjectId"], "source-project")
        self.assertNotEqual(output_data["projectId"], "source-project")
        self.assertEqual(report["outputProjectId"], output_data["projectId"])


if __name__ == "__main__":
    unittest.main()
