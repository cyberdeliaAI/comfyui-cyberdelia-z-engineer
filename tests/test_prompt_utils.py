import unittest

from prompt_utils import (
    build_preservation_instruction,
    contains_term,
    enforce_constraints,
    enforce_keep_terms,
    extract_constraints,
    parse_keep_terms,
    sanitize_output,
)


class PromptUtilsTests(unittest.TestCase):
    def test_sanitize_output_removes_wrappers_but_keeps_red(self):
        raw = (
            "<think>private reasoning</think>\n"
            "Final image prompt: A red dress under soft light. "
            "Negative prompt: blur, noise"
        )
        self.assertEqual(sanitize_output(raw), "A red dress under soft light.")

    def test_sanitize_output_removes_chatml_and_fences(self):
        raw = '<|im_start|>assistant\n```text\n"A polished prompt."```<|im_end|>'
        self.assertEqual(sanitize_output(raw), "A polished prompt.")

    def test_sanitize_output_removes_inline_negative_section(self):
        raw = "Positive prompt: A red robot in a studio Negative prompt: blur, text"
        self.assertEqual(sanitize_output(raw), "A red robot in a studio")

    def test_keep_terms_are_unique_and_use_complete_boundaries(self):
        terms = parse_keep_terms("m4rty style, OHWX woman; m4rty style\nneon_glow")
        self.assertEqual(terms, ["m4rty style", "OHWX woman", "neon_glow"])
        self.assertFalse(contains_term("cartoon", "art"))
        self.assertTrue(contains_term("fine art portrait", "art"))

    def test_enforce_keep_terms_preserves_original_case(self):
        result = enforce_keep_terms("A cinematic portrait.", ["OHWX woman", "m4rty style"])
        self.assertEqual(result, "A cinematic portrait, OHWX woman, m4rty style.")

    def test_extract_constraints_is_conservative(self):
        seed = (
            'three red robots holding a blue umbrella marked "OPEN 24H", '
            "RX-78, shot at 24-70mm f/2.8"
        )
        self.assertEqual(
            extract_constraints(seed),
            [
                "OPEN 24H",
                "24-70mm f/2.8",
                "RX-78",
                "three red robots",
                "blue umbrella",
            ],
        )

    def test_constraints_append_only_missing_terms(self):
        result = enforce_constraints(
            "Three red robots stand together.",
            ["three red robots", "blue umbrella"],
        )
        self.assertEqual(result, "Three red robots stand together, with blue umbrella.")

    def test_preservation_instruction_is_empty_without_features(self):
        self.assertEqual(build_preservation_instruction([], []), "")


if __name__ == "__main__":
    unittest.main()
