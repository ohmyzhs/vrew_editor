from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from vrew_auto_editor.dependencies import _extract_binary, _verify_checksum
from vrew_auto_editor.project import VrewError


class DependencyInstallerTests(unittest.TestCase):
    def test_extracts_binary_from_nested_archive_path(self) -> None:
        payload = b"fake ffprobe executable"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "ffmpeg.zip"
            destination = root / "ffprobe"
            with zipfile.ZipFile(archive, "w") as source:
                source.writestr("ffmpeg-8.1/bin/ffprobe", payload)

            _extract_binary(archive, "ffprobe", destination)

            self.assertEqual(destination.read_bytes(), payload)

    def test_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "ffmpeg.zip"
            archive.write_bytes(b"archive")

            with self.assertRaisesRegex(VrewError, "무결성 검증"):
                _verify_checksum(archive, hashlib.sha256(b"other").hexdigest())


if __name__ == "__main__":
    unittest.main()
