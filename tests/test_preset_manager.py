from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import preset_manager


class PresetManagerTests(unittest.TestCase):
    def test_bundled_cyberdelia_preset_is_available(self):
        presets = preset_manager.list_presets()
        names = [preset["name"] for preset in presets]
        self.assertIn("Cyberdelia Detailed 200-250", names)

    def test_user_presets_are_loaded_and_duplicate_names_remain_addressable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builtins = root / "builtins"
            users = root / "users"
            builtins.mkdir()
            users.mkdir()
            (builtins / "Shared.txt").write_text("Built-in prompt", encoding="utf-8")
            (users / "Shared.txt").write_text("User prompt", encoding="utf-8")
            (users / "Personal.txt").write_text("Personal prompt", encoding="utf-8")

            with (
                patch.object(preset_manager, "BUILTIN_PRESET_DIR", builtins),
                patch.object(preset_manager, "get_user_preset_dir", return_value=users),
            ):
                presets = preset_manager.list_presets()

        self.assertEqual(
            [(preset["name"], preset["prompt"]) for preset in presets],
            [
                ("Shared", "Built-in prompt"),
                ("Personal", "Personal prompt"),
                ("Shared (User)", "User prompt"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
