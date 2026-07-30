from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON = [
    ROOT / "build_sidecar.py",
    ROOT / "engine_main.py",
    *sorted((ROOT / "vrew_auto_editor").glob("*.py")),
]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


class EncodingPolicyTests(unittest.TestCase):
    def test_text_subprocesses_declare_utf8(self) -> None:
        failures: list[str] = []
        for path in PRODUCTION_PYTHON:
            tree = ast.parse(path.read_bytes(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if not (
                    isinstance(function, ast.Attribute)
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "subprocess"
                    and function.attr == "run"
                ):
                    continue
                text = _keyword(node, "text")
                universal = _keyword(node, "universal_newlines")
                text_mode = (
                    isinstance(text, ast.Constant)
                    and text.value is True
                    or isinstance(universal, ast.Constant)
                    and universal.value is True
                )
                if not text_mode:
                    continue
                encoding = _keyword(node, "encoding")
                if not (
                    isinstance(encoding, ast.Constant)
                    and str(encoding.value).casefold() == "utf-8"
                ):
                    failures.append(f"{path.name}:{node.lineno}")
        self.assertEqual(failures, [], f"UTF-8 없는 텍스트 subprocess: {failures}")

    def test_path_text_io_declares_utf8(self) -> None:
        failures: list[str] = []
        for path in PRODUCTION_PYTHON:
            tree = ast.parse(path.read_bytes(), filename=str(path))
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"read_text", "write_text"}
                ):
                    continue
                encoding = _keyword(node, "encoding")
                if not (
                    isinstance(encoding, ast.Constant)
                    and str(encoding.value).casefold() == "utf-8"
                ):
                    failures.append(f"{path.name}:{node.lineno}")
        self.assertEqual(failures, [], f"UTF-8 없는 텍스트 파일 I/O: {failures}")


if __name__ == "__main__":
    unittest.main()
