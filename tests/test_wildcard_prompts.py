import importlib.util
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from _requests_stub import ensure_requests

ensure_requests()

spec = importlib.util.spec_from_file_location("wildcard_nodes", Path(__file__).resolve().parents[1] / "wildcard_prompts.py")
nodes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nodes)


class EditablePromptTests(unittest.TestCase):
    def setUp(self):
        self.node = nodes.WildcardLoRAPrompts()

    def test_all_tag_names_can_be_added_renamed_or_removed(self):
        prompts, preview, count = self.node.expand(
            "An {subject} with {colour} hair, in a {outfit}, under {lighting}.",
            extra_tags="subject=adult man\ncolour=brown\noutfit=blue suit\nlighting=soft light",
        )
        self.assertEqual(prompts, ["An adult man with brown hair, in a blue suit, under soft light."])
        self.assertEqual(preview, prompts[0])
        self.assertEqual(count, 1)

    def test_hair_and_type_are_ordinary_tags_with_editable_values(self):
        result = self.node.expand("{type} with {hair} hair", extra_tags="hair=black\ntype=adult")
        self.assertEqual(result[0], ["adult with black hair"])

    def test_blank_line_mode_preserves_multiline_prompts(self):
        result = self.node.expand("First {hair}\r\ncontinued.\r\n\u00a0\r\nSecond {type}", mode="all prompts")
        self.assertEqual(result[0], ["First blonde\ncontinued.", "Second mature"])
        self.assertEqual(result[2], 2)

    def test_one_per_line_mode_ignores_empty_lines_and_keeps_order(self):
        result = self.node.expand(" First {hair}\r\ncontinued.\r\n \r\nSecond {type} \r\n", prompt_separator="one per line", mode="all prompts")
        self.assertEqual(result[0], ["First blonde", "continued.", "Second mature"])
        self.assertEqual(result[2], 3)

    def test_default_random_mode_sends_only_one_in_either_separator_mode(self):
        for separator, source in (("blank line", "First {hair}\n\nSecond {type}"), ("one per line", "First {hair}\nSecond {type}")):
            with self.subTest(separator=separator):
                result = self.node.expand(source, prompt_separator=separator)
                self.assertEqual(result[2], 1)
                self.assertEqual(len(result[0]), 1)
                self.assertIn(result[0][0], ("First blonde", "Second mature"))
                self.assertEqual(result[1], result[0][0])

    def test_invalid_separator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Choose 'blank line'"):
            self.node.expand("First", prompt_separator="unknown")

    def test_file_source_uses_the_selected_separator(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "test.txt"
            file.write_text("{hair}\n{type}", encoding="utf-8")
            result = self.node.expand("ignored", prompt_file=str(file), prompt_separator="one per line", mode="all prompts")
            self.assertEqual(result[0], ["blonde", "mature"])

    def test_tagless_prompts_can_use_an_empty_tag_field(self):
        self.assertEqual(self.node.expand("A landscape.", extra_tags="")[0], ["A landscape."])

    def test_tag_validation_still_catches_duplicate_and_malformed_names(self):
        for extra_tags in ("hair=blonde\nhair=brown", "hair blonde", "bad-name=blonde"):
            with self.subTest(extra_tags=extra_tags), self.assertRaises(ValueError):
                self.node.expand("{hair}", extra_tags=extra_tags)

    def test_tag_values_keep_equals_signs_and_comments_are_ignored(self):
        result = self.node.expand("{expression}", extra_tags="# note\n\nexpression=a=b")
        self.assertEqual(result[0], ["a=b"])

    def test_whole_word_replacement_avoids_substrings_and_accepts_punctuation(self):
        result = self.node.expand("The woman, superwoman, women and woman's coat.", search_replace="woman=male")
        self.assertEqual(result[0], ["The male, superwoman, women and male's coat."])

    def test_literal_text_mode_replaces_substrings(self):
        result = self.node.expand("woman and superwoman", search_replace="woman=male", replace_match="literal text")
        self.assertEqual(result[0], ["male and supermale"])

    def test_case_sensitive_option_and_default_case_insensitive_matching(self):
        source = "woman Woman WOMAN"
        self.assertEqual(self.node.expand(source, search_replace="woman=male")[0], ["male male male"])
        self.assertEqual(self.node.expand(source, search_replace="woman=male", case_sensitive=True)[0], ["male Woman WOMAN"])

    def test_replacement_matches_phrases_and_treats_regex_characters_literally(self):
        result = self.node.expand("red coat, redcoat, [x]", search_replace=r"red coat=blue suit" + "\n" + r"[x]=literal\1", replace_match="literal text")
        self.assertEqual(result[0], [r"blue suit, redcoat, literal\1"])

    def test_search_replace_runs_after_tags_are_filled(self):
        result = self.node.expand("A {subject} with {hair} hair.", extra_tags="subject=woman\nhair=blonde", search_replace="woman=male\nblonde=brown")
        self.assertEqual(result[0], ["A male with brown hair."])

    def test_rules_run_in_order_and_accept_equals_in_replacement(self):
        result = self.node.expand("woman", search_replace="woman=male\nmale=a=b")
        self.assertEqual(result[0], ["a=b"])

    def test_empty_replacement_deletes_text(self):
        result = self.node.expand("A red hat.", search_replace="red=")
        self.assertEqual(result[0], ["A  hat."])

    def test_comments_and_blank_replacement_rule_lines_are_ignored(self):
        result = self.node.expand("woman", search_replace="# comment\n\nwoman=male\n")
        self.assertEqual(result[0], ["male"])

    def test_invalid_rules_and_empty_result_are_rejected(self):
        for rules in ("=male", "no separator", "woman="):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                self.node.expand("woman", search_replace=rules)
        with self.assertRaisesRegex(ValueError, "Choose 'whole words'"):
            self.node.expand("woman", replace_match="unknown")

    def test_transformations_keep_the_seeded_prompt_selection(self):
        source = "First woman\n\nSecond woman\n\nThird woman"
        original = self.node.expand(source, prompt_seed=12345)
        replaced = self.node.expand(source, prompt_seed=12345, search_replace="woman=male")
        self.assertEqual(replaced[1], original[1].replace("woman", "male"))
        self.assertEqual(replaced[2], 1)

    def test_new_widgets_use_editable_tags_without_fixed_hair_type_inputs(self):
        schema = self.node.INPUT_TYPES()
        names = set(schema["required"]) | set(schema["optional"])
        self.assertNotIn("hair", names)
        self.assertNotIn("type", names)
        self.assertEqual(schema["required"]["extra_tags"][1]["default"], nodes.DEFAULT_TAGS)
        self.assertEqual(schema["optional"]["prompt_separator"][1]["default"], "blank line")
        self.assertEqual(schema["optional"]["mode"][1]["default"], "random prompt")

    def test_empty_prefix_including_whitespace_is_ignored(self):
        original = self.node.expand("A portrait.")
        self.assertEqual(original, self.node.expand("A portrait.", prefix=""))
        self.assertEqual(original, self.node.expand("A portrait.", prefix=" \t\n"))

    def test_prefix_is_added_to_final_prompts_and_preview(self):
        result = self.node.expand("First scene\n\nSecond scene", prefix="my_keyword", mode="all prompts")
        self.assertEqual(result[0], ["my_keyword, First scene", "my_keyword, Second scene"])
        self.assertEqual(result[1], "my_keyword, First scene\n\nmy_keyword, Second scene")
        self.assertEqual(result[2], 2)

    def test_prefix_with_trailing_comma_does_not_add_another_comma(self):
        self.assertEqual(self.node.expand("A portrait.", prefix=" my_keyword, ")[0], ["my_keyword, A portrait."])

    def test_prefix_can_use_tags_and_is_added_after_search_replace(self):
        result = self.node.expand("A woman.", extra_tags="trigger=woman", search_replace="woman=male", prefix="{trigger}")
        self.assertEqual(result[0], ["woman, A male."])

    def test_missing_or_empty_prefix_tags_are_ignored(self):
        for prefix in ("{trigger}", "{trigger}, {other}"):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.node.expand("A portrait.", extra_tags="trigger=", prefix=prefix)[0], ["A portrait."])

    def test_missing_and_empty_type_both_disappear_without_extra_spaces(self):
        source = "A portrait of a {type} woman with {hair} hair."
        for extra_tags in ("hair=blonde", "type=\nhair=blonde", "type=  \nhair=blonde"):
            with self.subTest(extra_tags=extra_tags):
                result = self.node.expand(source, extra_tags=extra_tags)
                self.assertEqual(result, (["A portrait of a woman with blonde hair."], "A portrait of a woman with blonde hair.", 1))

    def test_removing_tags_cleans_spaces_and_preserves_line_breaks(self):
        source = "{type} A {type} {outfit} woman {type}.\nwith {outfit} clothing {type}"
        self.assertEqual(self.node.expand(source, extra_tags="")[0], ["A woman.\nwith clothing"])

    def test_provided_tags_are_filled_and_unrelated_formatting_is_preserved(self):
        source = "A  {type} woman with {hair} hair."
        self.assertEqual(self.node.expand(source)[0], ["A  mature woman with blonde hair."])

    def test_values_are_inserted_literally_without_recursive_substitution(self):
        result = self.node.expand("{hair}", extra_tags=r"hair={type}\path" + "\n" + "type=mature")
        self.assertEqual(result[0], [r"{type}\path"])

    def test_a_prompt_containing_only_an_unfilled_tag_does_not_raise(self):
        self.assertEqual(self.node.expand("{type}", extra_tags=""), ([""], "", 1))
        self.assertEqual(self.node.expand("{type}", extra_tags="", prefix="keyword"), (["keyword"], "keyword", 1))

    def test_missing_tags_work_with_search_replace(self):
        self.assertEqual(self.node.expand("A {type} woman.", extra_tags="", search_replace="woman=male")[0], ["A male."])

    def test_random_selection_of_200_prompts_still_sends_one_and_keeps_seed(self):
        source = "\n\n".join(f"Scene {i}: a {{type}} woman with {{hair}} hair." for i in range(200))
        arguments = {"extra_tags": "hair=blonde", "prompt_seed": 12345}
        first = self.node.expand(source, **arguments)
        self.assertEqual(len(first[0]), 1)
        self.assertEqual(first[1], first[0][0])
        self.assertEqual(first[2], 1)
        self.assertNotIn("{type}", first[1])
        self.assertIn("a woman with blonde hair.", first[1])
        self.assertEqual(first, self.node.expand(source, **arguments))
        self.assertEqual(self.node.expand(source, mode="all prompts", **arguments)[2], 200)

    def test_prompt_selection_does_not_change_global_random_state(self):
        before = random.getstate()
        self.node.expand("First\n\nSecond", prompt_seed=42)
        self.assertEqual(before, random.getstate())

    def test_inline_choices_accept_arbitrary_words_and_phrases_with_existing_tags(self):
        arguments = {
            "prompts": "An adult {type} person with a { small | large } bag in {daylight|soft studio lighting}.",
            "prompt_seed": 42,
        }
        result = self.node.expand(**arguments)
        expected = {
            f"An adult mature person with a {size} bag in {light}."
            for size in ("small", "large")
            for light in ("daylight", "soft studio lighting")
        }
        self.assertIn(result[1], expected)
        self.assertEqual(result, self.node.expand(**arguments))

    def test_tag_choice_is_shared_by_repeated_uses_all_prompts_and_prefix(self):
        result = self.node.expand(
            "First {hair} hair and {hair} eyebrows.\n\nSecond {hair} hair.",
            extra_tags="hair={red|brown|black}", prefix="{hair}", mode="all prompts",
        )
        chosen = result[0][0].split(", ", 1)[0]
        self.assertIn(chosen, ("red", "brown", "black"))
        self.assertEqual(result[0], [
            f"{chosen}, First {chosen} hair and {chosen} eyebrows.",
            f"{chosen}, Second {chosen} hair.",
        ])
        self.assertEqual(result[2], 2)

    def test_replacement_choice_is_shared_by_all_matches_and_prompt_blocks(self):
        result = self.node.expand(
            "Straight hair and straight hair.\n\nAnother straight hair portrait.",
            search_replace="straight hair={red|brown|black} hair", mode="all prompts",
        )
        chosen = result[0][0].split()[0]
        self.assertIn(chosen, ("red", "brown", "black"))
        self.assertEqual(result[0], [
            f"{chosen} hair and {chosen} hair.",
            f"Another {chosen} hair portrait.",
        ])

    def test_choices_in_replacement_and_tag_values_preserve_literal_backslashes(self):
        for arguments in (
            {"prompts": "{size}", "extra_tags": r"size={small\1|large\2}"},
            {"prompts": "object", "search_replace": r"object={small\1|large\2}"},
        ):
            with self.subTest(arguments=arguments):
                self.assertIn(self.node.expand(**arguments)[1], (r"small\1", r"large\2"))

    def test_each_inline_choice_is_drawn_separately_and_seed_changes_results(self):
        results = {
            self.node.expand("{small|large} and {small|large}", prompt_seed=seed)[1]
            for seed in range(32)
        }
        self.assertEqual(results, {
            "small and small", "small and large", "large and small", "large and large",
        })

    def test_choices_do_not_change_which_prompt_block_is_selected(self):
        original = self.node.expand("First scene\n\nSecond scene\n\nThird scene", prompt_seed=12345)
        with_choices = self.node.expand(
            "First {size}\n\nSecond {small|large}\n\nThird {size}",
            extra_tags="size={small|large}", prefix="{day|night}", prompt_seed=12345,
        )
        selected = with_choices[1].split(", ", 1)[1].split()[0]
        self.assertEqual(selected, original[1].split()[0])

    def test_choice_draws_do_not_change_global_random_state(self):
        before = random.getstate()
        self.node.expand(
            "{size} object in {daylight|studio lighting}", extra_tags="size={small|large}",
            search_replace="object={bag|box}", prefix="{photo|illustration}", prompt_seed=42,
        )
        self.assertEqual(before, random.getstate())

    def test_all_prompts_fingerprint_tracks_choice_seed(self):
        arguments = {"prompts": "A {small|large} object", "mode": "all prompts"}
        self.assertNotEqual(
            self.node.IS_CHANGED(**arguments, prompt_seed=1),
            self.node.IS_CHANGED(**arguments, prompt_seed=2),
        )

    def test_disabled_choices_leave_fallback_exactly_unchanged(self):
        normal = "  A {small|large} object with {hair}.  "
        self.assertEqual(self.node.expand(
            "{day|night}", extra_tags="hair={red|brown|black}",
            search_replace="object={bag|box}", prefix="{photo|illustration}",
            enabled=False, fallback_prompt=normal,
        ), ([normal], normal, 1))

    def test_file_source_supports_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "prompts.txt"
            file.write_text("A {small|large} object with {hair} hair.", encoding="utf-8")
            result = self.node.expand(
                "ignored", prompt_file=str(file), extra_tags="hair={red|brown|black}",
            )
        self.assertIn(result[1], {
            f"A {size} object with {hair} hair."
            for size in ("small", "large")
            for hair in ("red", "brown", "black")
        })

    def test_file_edits_are_detected_and_override_pasted_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "prompts.txt"
            file.write_text("{type}\n\nA {hair} portrait.", encoding="utf-8")
            arguments = {"prompts": "ignored", "prompt_file": str(file), "extra_tags": "hair=blonde"}
            before = self.node.IS_CHANGED(**arguments)
            self.assertEqual(self.node.expand(**arguments, mode="all prompts")[0], ["", "A blonde portrait."])
            file.write_text("A {hair} portrait.\n\n{type}", encoding="utf-8")
            self.assertNotEqual(before, self.node.IS_CHANGED(**arguments))

    def test_relative_file_resolves_from_comfy_input(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "test.txt").write_text("{hair}", encoding="utf-8")
            folder_paths = types.SimpleNamespace(get_input_directory=lambda: directory)
            with patch.dict(sys.modules, {"folder_paths": folder_paths}):
                self.assertEqual(self.node.expand("", prompt_file="test.txt")[0], ["blonde"])

    def test_empty_source_and_invalid_files_still_have_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "at least one prompt"):
            self.node.expand(" \n\t")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaisesRegex(ValueError, "Cannot read prompt file"):
                self.node.expand("", prompt_file=str(path / "missing.txt"))
            with self.assertRaisesRegex(ValueError, "Choose a .txt file"):
                self.node.expand("", prompt_file=str(path / "file.csv"))
            (path / "bad.txt").write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                self.node.expand("", prompt_file=str(path / "bad.txt"))

    def test_disabled_sends_one_exact_normal_prompt_in_all_prompts_mode(self):
        source = "\n\n".join(f"Scene {number}" for number in range(200))
        normal = "  A {hair} woman.\n\nLeave this unchanged.  "
        self.assertEqual(
            self.node.expand(
                source, mode="all prompts", enabled=False,
                fallback_prompt=normal, extra_tags="hair=blonde",
                search_replace="woman=male", prefix="trigger",
            ),
            ([normal], normal, 1),
        )

    def test_disabled_bypasses_file_reads_and_all_wildcard_validation(self):
        arguments = {
            "prompts": "", "extra_tags": "invalid tags",
            "prompt_file": "/missing/file.csv", "prompt_separator": "invalid",
            "search_replace": "invalid", "replace_match": "invalid",
            "prefix": "{trigger}", "mode": "invalid", "enabled": False,
            "fallback_prompt": "Normal prompt",
        }
        with patch.object(nodes, "read_source", side_effect=AssertionError("File read while disabled")):
            self.assertEqual(self.node.IS_CHANGED(**arguments), ("wildcards-disabled",))
            self.assertEqual(self.node.expand(**arguments), (["Normal prompt"], "Normal prompt", 1))

    def test_disabled_empty_normal_prompt_is_one_empty_output(self):
        self.assertEqual(self.node.expand("", enabled=False), ([""], "", 1))

    def test_reenable_uses_wildcards_with_preserved_settings(self):
        arguments = {
            "prompts": "A {hair} woman", "extra_tags": "hair=blonde",
            "search_replace": "woman=male", "prefix": "trigger",
            "fallback_prompt": "Normal prompt",
        }
        self.assertEqual(self.node.expand(**arguments, enabled=False)[0], ["Normal prompt"])
        self.assertEqual(self.node.expand(**arguments, enabled=True)[0], ["trigger, A blonde male"])
        self.assertEqual(self.node.expand(**arguments)[0], ["trigger, A blonde male"])

    def test_toggle_widgets_are_appended_for_existing_workflows(self):
        inputs = self.node.INPUT_TYPES()
        self.assertTrue(inputs["optional"]["enabled"][1]["default"])
        self.assertEqual(list(inputs["optional"]), [
            "prompt_file", "prompt_separator", "search_replace", "replace_match",
            "case_sensitive", "prefix", "mode", "prompt_seed", "enabled",
            "fallback_prompt", "repeat_list", "sequence_index",
        ])

    def test_sequential_20_file_prompts_skip_last_10_of_30_runs(self):
        class ExecutionBlocker:
            def __init__(self, message):
                self.message = message

        graph = types.SimpleNamespace(ExecutionBlocker=ExecutionBlocker)
        expected = [f"Scene {number}" for number in range(1, 21)]
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"comfy_execution.graph": graph}):
            file = Path(directory) / "prompts.txt"
            file.write_text("\n".join(expected), encoding="utf-8")
            results = [self.node.expand(
                "ignored", prompt_file=str(file), prompt_separator="one per line",
                mode="sequential prompt", sequence_index=index,
            ) for index in range(30)]
        self.assertEqual([result[0][0] for result in results[:20]], expected)
        for prompts, preview, count in results[:20]:
            self.assertEqual((prompts, count), ([preview], 1))
        for prompts, preview, count in results[20:]:
            self.assertIsInstance(prompts[0], ExecutionBlocker)
            self.assertIs(prompts[0], preview)
            self.assertIsNone(preview.message)
            self.assertEqual(count, 0)

    def test_sequential_repeat_wraps_30_runs_over_20_prompts(self):
        expected = [f"Scene {number}" for number in range(1, 21)]
        results = [self.node.expand(
            "\n\n".join(expected), mode="sequential prompt", repeat_list=True,
            sequence_index=index,
        ) for index in range(30)]
        self.assertEqual([result[1] for result in results], expected + expected[:10])
        self.assertTrue(all(result[2] == 1 for result in results))

    def test_sequential_defaults_and_reset_do_not_depend_on_instance_state(self):
        inputs = self.node.INPUT_TYPES()
        self.assertFalse(inputs["optional"]["repeat_list"][1]["default"])
        self.assertEqual(inputs["optional"]["sequence_index"][1]["default"], 0)
        self.assertEqual(inputs["optional"]["mode"][0], ["random prompt", "sequential prompt", "all prompts"])
        for index, expected in ((1, "Second"), (0, "First"), (1, "Second")):
            # Replaying the same queued index is deterministic, including after
            # a restart or retry, and different node instances share no cursor.
            for node in (self.node, nodes.WildcardLoRAPrompts()):
                self.assertEqual(node.expand("First\n\nSecond", mode="sequential prompt", sequence_index=index), ([expected], expected, 1))

    def test_sequential_preserves_tags_choices_replacements_prefix_and_seed(self):
        arguments = dict(
            prompts="First {size} woman\n\nSecond {small|large} woman",
            extra_tags="size={small|large}", search_replace="woman=person",
            prefix="photo", prompt_seed=42,
        )
        all_prompts = self.node.expand(**arguments, mode="all prompts")[0]
        for index in range(2):
            result = self.node.expand(**arguments, mode="sequential prompt", sequence_index=index)
            self.assertEqual(result, ([all_prompts[index]], all_prompts[index], 1))
        # A changing prompt seed must not restart the sequence.
        self.assertTrue(self.node.expand(**{**arguments, "prompt_seed": 99}, mode="sequential prompt", sequence_index=1)[1].startswith("photo, Second"))

    def test_sequential_rejects_invalid_indices(self):
        for index in (-1, 1.5, "1", True):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "non-negative integer"):
                self.node.expand("First", mode="sequential prompt", sequence_index=index)

    def test_sequential_skipping_on_old_comfyui_fails_without_sending_empty_prompt(self):
        with patch.dict(sys.modules, {"comfy_execution.graph": None}):
            with self.assertRaisesRegex(RuntimeError, "Update ComfyUI"):
                self.node.expand("First", mode="sequential prompt", sequence_index=1)

    def test_new_sequence_options_do_not_change_legacy_modes_or_disabled_passthrough(self):
        for mode in ("random prompt", "all prompts"):
            arguments = dict(prompts="First\n\nSecond", mode=mode, prompt_seed=42)
            self.assertEqual(self.node.expand(**arguments), self.node.expand(**arguments, sequence_index=30, repeat_list=True))
        self.assertEqual(self.node.expand(
            "First", mode="sequential prompt", sequence_index=30,
            enabled=False, fallback_prompt="  Exact {tag}  ",
        ), (["  Exact {tag}  "], "  Exact {tag}  ", 1))

    def test_sequential_file_fingerprint_still_detects_content_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "prompts.txt"
            file.write_text("First", encoding="utf-8")
            arguments = dict(prompt_file=str(file), mode="sequential prompt", sequence_index=1)
            before = self.node.IS_CHANGED(**arguments)
            file.write_text("First\n\nSecond", encoding="utf-8")
            self.assertNotEqual(before, self.node.IS_CHANGED(**arguments))
            self.assertEqual(self.node.expand("", **arguments)[1], "Second")

    def test_package_preserves_engineer_nodes_and_current_wildcard_id(self):
        package_path = Path(__file__).resolve().parents[1]
        package_spec = importlib.util.spec_from_file_location("wildcard_lora_test", package_path / "__init__.py", submodule_search_locations=[str(package_path)])
        package = importlib.util.module_from_spec(package_spec)
        with patch.dict(sys.modules, {package_spec.name: package}):
            package_spec.loader.exec_module(package)
            self.assertIn("WildcardLoRAPromptsV3", package.NODE_CLASS_MAPPINGS)
            self.assertIn("CyberdeliaZEngineer", package.NODE_CLASS_MAPPINGS)
            self.assertIn("CyberdeliaPromptEngineerText", package.NODE_CLASS_MAPPINGS)
            self.assertNotIn("WildcardLoRAPrompts", package.NODE_CLASS_MAPPINGS)
            self.assertEqual(package.NODE_DISPLAY_NAME_MAPPINGS["WildcardLoRAPromptsV3"], "Cyberdelia Wildcard Prompts")
            self.assertFalse(hasattr(nodes, "LegacyWildcardLoRAPrompts"))
            self.assertEqual(self.node.OUTPUT_IS_LIST, (True, False, False))
            self.assertTrue((package_path / package.WEB_DIRECTORY / "js/wildcard_prompts.js").is_file())
            normal = "Normal prompt"
            for enabled, expected in ((False, normal), (True, "A blonde portrait")):
                selected, _, count = self.node.expand(
                    "A {hair} portrait", fallback_prompt=normal, enabled=enabled,
                )
                self.assertEqual(count, 1)
                engineer = package.NODE_CLASS_MAPPINGS["CyberdeliaPromptEngineerText"]()
                self.assertEqual(engineer.generate_text(
                    mode=False, text=selected[0], system_prompt="",
                    api_url="", model="", seed=0, temperature=0.7,
                    max_tokens=600, timeout=120,
                ), (expected,))


if __name__ == "__main__":
    unittest.main()
