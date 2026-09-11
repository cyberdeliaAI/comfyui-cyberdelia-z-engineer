import importlib.util
from pathlib import Path
import sys
import unittest

from _requests_stub import ensure_requests

ensure_requests()


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "cyberdelia_z_engineer_test_package"
if PACKAGE_NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = package
    spec.loader.exec_module(package)

package = sys.modules[PACKAGE_NAME]
input_module = sys.modules[f"{PACKAGE_NAME}.z_engineer_input"]
preset_input_module = sys.modules[f"{PACKAGE_NAME}.prompt_preset_controls"]
CyberdeliaZEngineerInput = input_module.CyberdeliaZEngineerInput
CyberdeliaPromptPresetControls = preset_input_module.CyberdeliaPromptPresetControls


class InputNodeTests(unittest.TestCase):
    def test_node_is_registered(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaZEngineerInput"],
            CyberdeliaZEngineerInput,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaZEngineerInput"],
            "Cyberdelia Prompt Controls",
        )
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaPromptPresetControls"],
            CyberdeliaPromptPresetControls,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaPromptPresetControls"],
            "Cyberdelia Prompt Controls — Presets",
        )

    def test_mode_and_prompt_outputs_match_z_engineer_inputs(self):
        self.assertEqual(
            list(CyberdeliaZEngineerInput.INPUT_TYPES()["required"]),
            ["mode", "prompt"],
        )
        self.assertEqual(
            list(CyberdeliaZEngineerInput.INPUT_TYPES()["optional"]),
            ["use_vision"],
        )
        self.assertEqual(
            CyberdeliaZEngineerInput.RETURN_TYPES,
            ("BOOLEAN", "STRING", "BOOLEAN"),
        )
        self.assertEqual(
            CyberdeliaZEngineerInput.RETURN_NAMES,
            ("mode", "prompt", "use_vision"),
        )

    def test_values_are_returned_unchanged(self):
        node = CyberdeliaZEngineerInput()
        prompt = "First line\nSecond line"
        self.assertEqual(node.route(True, prompt), (True, prompt, False))
        self.assertEqual(node.route(True, prompt, False), (True, prompt, False))
        self.assertEqual(node.route(False, prompt, True), (False, prompt, True))

    def test_legacy_outputs_remain_first(self):
        self.assertEqual(
            CyberdeliaZEngineerInput.RETURN_NAMES,
            ("mode", "prompt", "use_vision"),
        )

    def test_preset_controls_append_active_system_prompt(self):
        inputs = CyberdeliaPromptPresetControls.INPUT_TYPES()
        self.assertEqual(list(inputs["required"]), ["mode", "prompt"])
        self.assertEqual(
            list(inputs["optional"]),
            ["use_vision", "active_system_prompt"],
        )
        self.assertEqual(
            CyberdeliaPromptPresetControls.RETURN_NAMES,
            ("mode", "prompt", "use_vision", "active_system_prompt"),
        )

        node = CyberdeliaPromptPresetControls()
        self.assertEqual(
            node.route(True, "A prompt", True, "Vision instructions"),
            (True, "A prompt", True, "Vision instructions"),
        )


if __name__ == "__main__":
    unittest.main()
