"""Prompt-only Cyberdelia Prompt Engineer node."""

from copy import deepcopy

from .z_engineer import CyberdeliaZEngineer


class CyberdeliaPromptEngineerText(CyberdeliaZEngineer):
    """Generate a text or vision prompt without requiring a CLIP model."""

    @classmethod
    def INPUT_TYPES(cls):
        inputs = deepcopy(super().INPUT_TYPES())
        inputs["required"].pop("clip", None)
        return inputs

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate_text"
    CATEGORY = "Cyberdelia/Prompt"

    def generate_text(self, mode, text, system_prompt,
                      api_url, model, seed, temperature, max_tokens, timeout,
                      keep_terms="", preserve_constraints=False,
                      clean_output=True, error_mode="fallback_input", retries=1,
                      use_vision=False, vision_system_prompt="", image=None):
        final_text = self._generate_final_text(
            mode, text, system_prompt, api_url, model, seed, temperature,
            max_tokens, timeout, keep_terms, preserve_constraints, clean_output,
            error_mode, retries, use_vision, vision_system_prompt, image,
        )
        return (final_text,)
