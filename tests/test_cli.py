from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from vrew_auto_editor.cli import configure_utf8_stdio, serialize_cli_json


class CliEncodingTests(unittest.TestCase):
    def test_configures_utf8_for_child_processes(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configure_utf8_stdio()
            self.assertEqual(os.environ["PYTHONUTF8"], "1")
            self.assertEqual(os.environ["PYTHONIOENCODING"], "utf-8")

    def test_sidecar_json_is_ascii_and_round_trips_korean_windows_paths(
        self,
    ) -> None:
        payload = {
            "source": r"C:\작업\민담\영상작업용\03\영상.vrew",
            "script": r"C:\작업\민담\영상작업용\03\대본_flow_prompts.txt",
            "output": r"C:\작업\민담\영상작업용\03\영상_작업완료.vrew",
        }

        serialized = serialize_cli_json(payload)

        serialized.encode("ascii")
        self.assertEqual(json.loads(serialized), payload)
        self.assertIn("\\uc791\\uc5c5", serialized)
