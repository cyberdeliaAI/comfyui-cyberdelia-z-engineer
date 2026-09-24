import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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
chain_module = sys.modules[f"{PACKAGE_NAME}.prompt_chain"]
CyberdeliaPromptEngineerChain = chain_module.CyberdeliaPromptEngineerChain


class PromptChainTests(unittest.TestCase):
    def setUp(self):
        self.node = CyberdeliaPromptEngineerChain()
        self.base_args = {
            "mode": True,
            "text": "a lighthouse in a storm",
            "stage_count": 3,
            "handoff_mode": chain_module.PREVIOUS_OUTPUT_ONLY,
            "system_prompt_1": "Stage A",
            "system_prompt_2": "Stage B",
            "system_prompt_3": "Stage C",
            "system_prompt_4": "Stage D",
            "system_prompt_5": "Stage E",
            "api_url": "http://localhost:1234/v1",
            "model": "manual-model",
            "seed": 0,
            "temperature": 0.7,
            "max_tokens": 600,
            "timeout": 120,
        }

    def test_node_is_registered(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaPromptEngineerChain"],
            CyberdeliaPromptEngineerChain,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaPromptEngineerChain"],
            "Cyberdelia Prompt Engineer — Chain",
        )

    def test_node_has_five_configurable_stages_and_intermediate_outputs(self):
        required = CyberdeliaPromptEngineerChain.INPUT_TYPES()["required"]
        for index in range(1, 6):
            self.assertIn(f"system_prompt_{index}", required)
        self.assertEqual(
            CyberdeliaPromptEngineerChain.RETURN_NAMES,
            ("final_prompt", "stage_1", "stage_2", "stage_3", "stage_4", "stage_5"),
        )

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_previous_output_is_passed_to_the_next_stage(self, resolve_model):
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=["after A", "after B", "after C"],
        ) as generate:
            result = self.node.run_chain(**self.base_args)

        self.assertEqual(result, ("after C", "after A", "after B", "after C", "", ""))
        self.assertEqual(generate.call_args_list[0].args[1], "a lighthouse in a storm")
        self.assertEqual(generate.call_args_list[0].args[2], "Stage A")
        self.assertEqual(generate.call_args_list[1].args[1], "after A")
        self.assertEqual(generate.call_args_list[1].args[2], "Stage B")
        self.assertEqual(generate.call_args_list[2].args[1], "after B")
        self.assertEqual(generate.call_args_list[2].args[2], "Stage C")
        resolve_model.assert_called_once_with(
            "manual-model",
            "http://localhost:1234/v1",
            timeout=120,
            require_vision=False,
        )

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_original_and_previous_handoff_includes_both(self, _resolve_model):
        args = {
            **self.base_args,
            "stage_count": 2,
            "handoff_mode": chain_module.ORIGINAL_AND_PREVIOUS,
        }
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=["after A", "after B"],
        ) as generate:
            result = self.node.run_chain(**args)

        second_input = generate.call_args_list[1].args[1]
        self.assertIn("Original prompt:\na lighthouse in a storm", second_input)
        self.assertIn("Previous stage output:\nafter A", second_input)
        self.assertEqual(result[0], "after B")

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_stage_count_limits_calls(self, _resolve_model):
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=["after A", "after B"],
        ) as generate:
            result = self.node.run_chain(**{**self.base_args, "stage_count": 2})

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result, ("after B", "after A", "after B", "", "", ""))

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_empty_system_prompt_skips_that_stage(self, _resolve_model):
        args = {**self.base_args, "system_prompt_2": ""}
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=["after A", "after C"],
        ) as generate:
            result = self.node.run_chain(**args)

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result, ("after C", "after A", "after A", "after C", "", ""))

    @patch.object(chain_module, "resolve_model_name")
    def test_passthrough_does_not_resolve_or_call_model(self, resolve_model):
        with patch.object(self.node, "_generate_final_text") as generate:
            result = self.node.run_chain(**{**self.base_args, "mode": False})

        self.assertEqual(result, ("a lighthouse in a storm", "", "", "", "", ""))
        resolve_model.assert_not_called()
        generate.assert_not_called()

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_fallback_keeps_previous_output_and_continues(self, _resolve_model):
        args = {**self.base_args, "error_mode": "fallback_input"}
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=["after A", RuntimeError("stage failed"), "after C"],
        ) as generate:
            result = self.node.run_chain(**args)

        self.assertEqual(generate.call_args_list[2].args[1], "after A")
        self.assertEqual(result, ("after C", "after A", "after A", "after C", "", ""))

    @patch.object(chain_module, "resolve_model_name", return_value="resolved-model")
    def test_stop_mode_propagates_stage_failure(self, _resolve_model):
        with patch.object(
            self.node,
            "_generate_final_text",
            side_effect=RuntimeError("stage failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stage failed"):
                self.node.run_chain(**self.base_args)


if __name__ == "__main__":
    unittest.main()
