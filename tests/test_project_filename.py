from __future__ import annotations

import unittest

from vrew_auto_editor.project import VrewError, validate_windows_filename


class WindowsFilenameTests(unittest.TestCase):
    def test_allows_unicode_vrew_filename(self) -> None:
        validate_windows_filename("영상09_작업완료.vrew")

    def test_rejects_invalid_character_with_codepoint(self) -> None:
        with self.assertRaisesRegex(VrewError, r"U\+003F"):
            validate_windows_filename("영상?_작업완료.vrew")

    def test_rejects_trailing_dot_or_space(self) -> None:
        for name in ("영상.vrew.", "영상.vrew "):
            with self.subTest(name=name), self.assertRaises(VrewError):
                validate_windows_filename(name)

    def test_rejects_reserved_device_name_with_extension(self) -> None:
        with self.assertRaisesRegex(VrewError, "CON"):
            validate_windows_filename("con.vrew")

    def test_counts_utf16_code_units(self) -> None:
        validate_windows_filename(f"{'가' * 250}.vrew")
        with self.assertRaisesRegex(VrewError, "256"):
            validate_windows_filename(f"{'가' * 251}.vrew")


if __name__ == "__main__":
    unittest.main()
