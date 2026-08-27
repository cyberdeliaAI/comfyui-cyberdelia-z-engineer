import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from _requests_stub import ensure_requests

requests = ensure_requests()


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
node_module = sys.modules[f"{PACKAGE_NAME}.danbooru_node"]
llm_module = sys.modules[f"{PACKAGE_NAME}.z_engineer"]
CyberdeliaDanbooruPrompt = node_module.CyberdeliaDanbooruPrompt


def response_with(content):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


class DanbooruNodeTests(unittest.TestCase):
    def setUp(self):
        self.node = CyberdeliaDanbooruPrompt()
        self.base_args = {
            "text": "a blonde girl in a black crop top",
            "system_prompt": node_module.DEFAULT_SYSTEM_PROMPT,
            "prompt_template": "{prompt}",
            "api_url": "http://localhost:1234/v1",
            "model": "manual-model",
            "seed": 0,
            "temperature": 0.4,
            "max_tokens": 500,
            "timeout": 120,
            "tag_format": "spaces",
        }

    def test_node_is_registered(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaDanbooruPrompt"],
            CyberdeliaDanbooruPrompt,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaDanbooruPrompt"],
            "Cyberdelia Danbooru Prompt",
        )
        self.assertEqual(
            CyberdeliaDanbooruPrompt.RETURN_NAMES,
            ("prompt", "tags", "dropped_tags"),
        )

    def test_format_widget_has_spaces_and_underscores(self):
        widget = CyberdeliaDanbooruPrompt.INPUT_TYPES()["required"]["tag_format"]
        self.assertEqual(widget[0], ["spaces", "underscores"])
        self.assertEqual(widget[1]["default"], "spaces")

    def test_generates_validated_space_tags(self):
        with patch.object(
            llm_module.requests,
            "post",
            return_value=response_with(
                "1girl, blonde, black crop top, arms crossed, qzx nonsense"
            ),
        ):
            prompt, tags, dropped = self.node.generate(**self.base_args)

        self.assertEqual(
            tags,
            "1girl, blonde hair, crop top, crossed arms",
        )
        self.assertEqual(prompt, tags)
        self.assertEqual(dropped, "black crop top, qzx nonsense")

    def test_generates_underscore_tags_and_applies_template(self):
        with patch.object(
            llm_module.requests,
            "post",
            return_value=response_with("blue eyes, long hair, 1girl"),
        ) as post:
            prompt, tags, dropped = self.node.generate(
                **{
                    **self.base_args,
                    "tag_format": "underscores",
                    "prompt_template": "quality, {prompt}",
                },
            )

        self.assertEqual(tags, "1girl, blue_eyes, long_hair")
        self.assertEqual(prompt, "quality, 1girl, blue_eyes, long_hair")
        self.assertEqual(dropped, "")
        system_prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("underscores between words", system_prompt)
        self.assertTrue(system_prompt.endswith("/no_think"))

    def test_template_preset_overrides_custom_template(self):
        with patch.object(
            llm_module.requests,
            "post",
            return_value=response_with("1girl, beach"),
        ):
            prompt, tags, _dropped = self.node.generate(
                **{**self.base_args, "prompt_template": "ignored, {prompt}"},
                template_preset="pony",
            )

        self.assertEqual(tags, "1girl, beach")
        self.assertTrue(prompt.startswith("score_9, score_8_up"))
        self.assertNotIn("ignored", prompt)

    def test_validation_can_be_disabled_but_format_is_applied(self):
        with patch.object(
            llm_module.requests,
            "post",
            return_value=response_with("made up tag, blue eyes"),
        ):
            prompt, tags, dropped = self.node.generate(
                **{**self.base_args, "tag_format": "underscores"},
                validate_tags=False,
            )

        self.assertEqual(tags, "made_up_tag, blue_eyes")
        self.assertEqual(prompt, tags)
        self.assertEqual(dropped, "")

    def test_fallback_preserves_natural_input(self):
        with patch.object(
            llm_module.requests,
            "post",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            prompt, tags, dropped = self.node.generate(
                **self.base_args,
                retries=0,
                error_mode="fallback_input",
            )

        self.assertEqual(tags, self.base_args["text"])
        self.assertEqual(prompt, self.base_args["text"])
        self.assertEqual(dropped, "")

    def test_empty_input_does_not_call_the_llm(self):
        with patch.object(llm_module.requests, "post") as post:
            result = self.node.generate(**{**self.base_args, "text": ""})
        self.assertEqual(result, ("", "", ""))
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
