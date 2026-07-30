from __future__ import annotations

import unittest
from unittest.mock import patch

from vrew_auto_editor.picker import _run


class PickerEncodingTests(unittest.TestCase):
    @patch("vrew_auto_editor.picker.subprocess.run")
    def test_decodes_utf8_path_without_windows_codepage(self, run) -> None:
        run.return_value.returncode = 0
        run.return_value.stdout = "C:\\작업\\영상.vrew\r\n".encode("utf-8")
        run.return_value.stderr = b""

        result = _run(["powershell.exe"])

        self.assertEqual(result, "C:\\작업\\영상.vrew")
        self.assertNotIn("text", run.call_args.kwargs)
        self.assertNotIn("encoding", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
