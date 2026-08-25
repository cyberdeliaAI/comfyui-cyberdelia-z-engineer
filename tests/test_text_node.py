import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

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
node_module = sys.modules[f"{PACKAGE_NAME}.z_engineer"]
text_module = sys.modules[f"{PACKAGE_NAME}.prompt_engineer_text"]
CyberdeliaPromptEngineerText = text_module.CyberdeliaPromptEngineerText


def response_with(content):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


class TextNodeTests(unittest.TestCase):
    def setUp(self):
        self.node = CyberdeliaPromptEngineerText()
        self.base_args = {
            "mode": True,
            "text": "a lighthouse in a storm",
            "system_prompt": "Return an image prompt.",
            "api_url": "http://localhost:1234/v1",
            "model": "manual-model",
            "seed": 0,
            "temperature": 0.7,
            "max_tokens": 600,
            "timeout": 120,
        }

    def test_node_is_registered_without_changing_legacy_ids(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaPromptEngineerText"],
            CyberdeliaPromptEngineerText,
        )
        self.assertIn("CyberdeliaZEngineer", package.NODE_CLASS_MAPPINGS)
        self.assertIn("CyberdeliaZEngineerInput", package.NODE_CLASS_MAPPINGS)
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaZEngineer"],
            "Cyberdelia Prompt Engineer — Conditioning",
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaPromptEngineerText"],
            "Cyberdelia Prompt Engineer — Text",
        )

    def test_text_node_has_no_clip_and_only_string_output(self):
        inputs = CyberdeliaPromptEngineerText.INPUT_TYPES()
        self.assertNotIn("clip", inputs["required"])
        self.assertNotIn("clip", inputs["optional"])
        self.assertEqual(CyberdeliaPromptEngineerText.RETURN_TYPES, ("STRING",))
        self.assertEqual(CyberdeliaPromptEngineerText.RETURN_NAMES, ("prompt",))
        self.assertEqual(
            list(inputs["optional"]),
            list(package.NODE_CLASS_MAPPINGS["CyberdeliaZEngineer"].INPUT_TYPES()["optional"]),
        )

    def test_normal_prompt_generation_requires_no_clip(self):
        with patch.object(
            node_module.requests,
            "post",
            return_value=response_with("Final prompt: A dramatic lighthouse."),
        ) as post:
            result = self.node.generate_text(**self.base_args)

        self.assertEqual(result, ("A dramatic lighthouse.",))
        self.assertEqual(
            post.call_args.kwargs["json"]["messages"][1]["content"],
            "a lighthouse in a storm",
        )

    def test_vision_prompt_generation_requires_no_clip(self):
        with (
            patch.object(
                node_module,
                "image_to_data_url",
                return_value="data:image/jpeg;base64,example",
            ),
            patch.object(
                node_module.requests,
                "post",
                return_value=response_with("A detailed vision prompt."),
            ) as post,
        ):
            result = self.node.generate_text(
                **self.base_args,
                use_vision=True,
                vision_system_prompt="Describe only visible details.",
                image=object(),
            )

        self.assertEqual(result, ("A detailed vision prompt.",))
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(messages[0]["content"], "Describe only visible details.")
        self.assertIsInstance(messages[1]["content"], list)

    def test_passthrough_does_not_call_api(self):
        with patch.object(node_module.requests, "post") as post:
            result = self.node.generate_text(
                **{**self.base_args, "mode": False},
            )

        self.assertEqual(result, ("a lighthouse in a storm",))
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
