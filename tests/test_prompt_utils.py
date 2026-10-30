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

    def test_enforce_keep_terms_restores_casing_and_spacing_in_place(self):
        result = enforce_keep_terms(
            "A cyberrealistic portrait of an ohwx  woman, CYBERREALISTIC style.",
            ["CyberRealistic", "OHWX woman"],
        )
        self.assertEqual(result, "A CyberRealistic portrait of an OHWX woman, CyberRealistic style.")

    def test_overlapping_keep_terms_preserve_both_exact_spellings(self):
        for terms in (["OHWX Woman", "woman"], ["woman", "OHWX Woman"]):
            with self.subTest(terms=terms):
                result = enforce_keep_terms("A portrait of an ohwx  woman.", terms)
                self.assertEqual(result, "A portrait of an OHWX Woman, woman.")

    def test_compatible_overlapping_terms_need_no_duplicates(self):
        result = enforce_keep_terms("An OHWX WOMAN in a studio.", ["woman", "OHWX woman"])
        self.assertEqual(result, "An OHWX woman in a studio.")

    def test_overlapping_terms_keep_separate_existing_occurrences(self):
        result = enforce_keep_terms("OHWX woman beside another WOMAN.", ["OHWX Woman", "woman"])
        self.assertEqual(result, "OHWX Woman beside another woman.")

    def test_overlapping_term_matches_use_complete_boundaries(self):
        result = enforce_keep_terms("A cyberrealistic style, not a cart.", ["CyberRealistic Style", "style", "art"])
        self.assertEqual(result, "A CyberRealistic Style, not a cart, style, art.")

    def test_restoring_overlapping_terms_is_idempotent(self):
        terms = ["OHWX Woman", "woman"]
        first = enforce_keep_terms("OHWX WOMAN", terms)
        self.assertEqual(enforce_keep_terms(first, terms), first)

    def test_sanitize_output_removes_common_preambles(self):
        for raw in (
            "Here's the prompt: a cat on a mat",
            "Here’s your final prompt: a cat on a mat",
            "Sure! Here is the enhanced prompt:\n\na cat on a mat",
            "Certainly, here is the refined image prompt - a cat on a mat",
            "Image generation prompt: a cat on a mat",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(sanitize_output(raw), "a cat on a mat")

    def test_sanitize_output_keeps_words_that_only_start_with_prompt(self):
        self.assertEqual(sanitize_output("Prompt-engineered look, a cat"), "Prompt-engineered look, a cat")
        self.assertEqual(sanitize_output("Sure footed goat on a cliff"), "Sure footed goat on a cliff")

    def test_extract_constraints_ignores_counts_without_an_object(self):
        self.assertEqual(
            extract_constraints("one of the women holds two red apples"),
            ["two red apples"],
        )


if __name__ == "__main__":
    unittest.main()
