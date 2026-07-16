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
CyberdeliaZEngineerInput = input_module.CyberdeliaZEngineerInput


class InputNodeTests(unittest.TestCase):
    def test_node_is_registered(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaZEngineerInput"],
            CyberdeliaZEngineerInput,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaZEngineerInput"],
            "Cyberdelia Z-Engineer Input",
        )

    def test_mode_and_prompt_outputs_match_z_engineer_inputs(self):
        self.assertEqual(
            list(CyberdeliaZEngineerInput.INPUT_TYPES()["required"]),
            ["mode", "prompt"],
        )
        self.assertEqual(CyberdeliaZEngineerInput.RETURN_TYPES, ("BOOLEAN", "STRING"))
        self.assertEqual(CyberdeliaZEngineerInput.RETURN_NAMES, ("mode", "prompt"))

    def test_values_are_returned_unchanged(self):
        node = CyberdeliaZEngineerInput()
        prompt = "First line\nSecond line"
        self.assertEqual(node.route(True, prompt), (True, prompt))
        self.assertEqual(node.route(False, prompt), (False, prompt))


if __name__ == "__main__":
    unittest.main()
