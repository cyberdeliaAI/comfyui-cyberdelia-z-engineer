"""Cyberdelia Danbooru Prompt ComfyUI node."""

from .danbooru_tags import (
    format_tag,
    get_tag_db,
    normalize_tag,
    parse_categories,
)
from .model_utils import resolve_model_name
from .prompt_utils import sanitize_output
from .z_engineer import CyberdeliaZEngineer


DEFAULT_SYSTEM_PROMPT = (
    "You convert a scene description into Danbooru tags for an anime image model. "
    "Output only lowercase tags separated by commas. Do not write sentences, "
    "explanations, numbering, headings, or category names. Use canonical Danbooru "
    "concepts such as 'blue eyes', 'long hair', '1girl', and 'crossed arms'. "
    "Do not add quality tags such as masterpiece, best quality, absurdres, or "
    "score_9 because those can be added by the prompt template.\n"
    "Example input: a cheerful blonde girl in a red dress on a beach at sunset\n"
    "Example output: 1girl, blonde hair, long hair, smile, red dress, beach, "
    "sunset, ocean, sky, cloud, standing\n"
    "Return tags only. /no_think"
)

TEMPLATE_PRESETS = {
    "tags_only": "{prompt}",
    "illustrious": "masterpiece, best quality, very aesthetic, absurdres, {prompt}",
    "pony": "score_9, score_8_up, score_7_up, source_anime, {prompt}",
    "animagine_xl": "{prompt}, masterpiece, best quality, very aesthetic, absurdres",
    "nova_anime_xl": (
        "masterpiece, best quality, amazing quality, 4k, very aesthetic, "
        "high resolution, ultra-detailed, absurdres, newest, scenery, "
        "{prompt}, BREAK, depth of field, volumetric lighting"
    ),
}


def apply_prompt_template(template, prompt):
    """Insert tags into a template without silently discarding them."""
    template = str(template or "")
    prompt = str(prompt or "")
    if "{prompt}" in template:
        return template.replace("{prompt}", prompt)
    if not template.strip():
        return prompt
    if not prompt:
        return template.strip()
    print("[Danbooru Prompt] Template has no {prompt} placeholder; appending tags")
    return f"{template.rstrip().rstrip(',')}, {prompt}"


def format_unvalidated_tags(text, tag_format):
    """Apply the selected display format without claiming tags are valid."""
    formatted = []
    for candidate in (part.strip() for part in str(text or "").split(",")):
        if candidate:
            formatted.append(format_tag(normalize_tag(candidate), tag_format))
    return ", ".join(formatted)


class CyberdeliaDanbooruPrompt(CyberdeliaZEngineer):
    """Convert natural language to validated Danbooru tags with a local LLM."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Describe the anime scene...",
                    "tooltip": "Natural-language scene description to convert into tags.",
                }),
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": DEFAULT_SYSTEM_PROMPT,
                    "tooltip": "Instructions used by the LLM to propose Danbooru tags.",
                }),
                "prompt_template": ("STRING", {
                    "multiline": True,
                    "default": "{prompt}",
                    "tooltip": "Final wrapper. {prompt} is replaced with validated tags.",
                }),
                "api_url": ("STRING", {
                    "multiline": False,
                    "default": "http://localhost:1234/v1",
                }),
                "model": ("STRING", {
                    "multiline": False,
                    "default": "auto",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffff,
                    "control_after_generate": True,
                }),
                "temperature": ("FLOAT", {
                    "default": 0.4,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                }),
                "max_tokens": ("INT", {
                    "default": 500,
                    "min": 50,
                    "max": 4096,
                    "step": 10,
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 10,
                    "max": 600,
                    "step": 1,
                }),
                "tag_format": (["spaces", "underscores"], {
                    "default": "spaces",
                    "tooltip": "Render tags as 'blue eyes' or 'blue_eyes'.",
                }),
            },
            "optional": {
                "validate_tags": ("BOOLEAN", {
                    "default": True,
                    "label_on": "validate against Danbooru",
                    "label_off": "keep LLM candidates",
                }),
                "strict_tags": ("BOOLEAN", {
                    "default": True,
                    "label_on": "drop unknown tags",
                    "label_off": "keep unknown tags",
                }),
                "fuzzy_cutoff": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "0 disables fuzzy matching; 0.85 or higher is safest.",
                }),
                "min_post_count": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000000,
                    "step": 100,
                }),
                "max_tags": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 200,
                    "step": 1,
                    "tooltip": "0 means no tag limit.",
                }),
                "exclude_categories": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "artist, character, copyright, meta...",
                }),
                "sort_tags": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Danbooru order",
                    "label_off": "LLM order",
                }),
                "template_preset": (["custom", *TEMPLATE_PRESETS], {
                    "default": "custom",
                }),
                "error_mode": (["stop", "fallback_input", "empty"], {
                    "default": "stop",
                }),
                "retries": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 3,
                    "step": 1,
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "tags", "dropped_tags")
    OUTPUT_TOOLTIPS = (
        "Validated tags wrapped in the selected prompt template.",
        "Validated tags without template text.",
        "Candidates removed or only partially recovered during validation.",
    )
    FUNCTION = "generate"
    CATEGORY = "Cyberdelia/Prompt"

    def generate(
        self,
        text,
        system_prompt,
        prompt_template,
        api_url,
        model,
        seed,
        temperature,
        max_tokens,
        timeout,
        tag_format,
        validate_tags=True,
        strict_tags=True,
        fuzzy_cutoff=0.0,
        min_post_count=0,
        max_tags=0,
        exclude_categories="",
        sort_tags=True,
        template_preset="custom",
        error_mode="stop",
        retries=1,
    ):
        input_text = str(text or "")
        if not input_text.strip():
            return ("", "", "")

        resolved_model = str(model or "").strip() or "auto"
        is_fallback = False
        try:
            resolved_model = resolve_model_name(
                model,
                api_url,
                timeout=timeout,
                require_vision=False,
            )
            format_instruction = (
                "Write each candidate tag with underscores between words."
                if tag_format == "underscores"
                else "Write each candidate tag with spaces between words, not underscores."
            )
            prompt_instructions = str(system_prompt or "").strip()
            no_think_suffix = ""
            if prompt_instructions.casefold().endswith("/no_think"):
                prompt_instructions = prompt_instructions[: -len("/no_think")].rstrip()
                no_think_suffix = "\n/no_think"
            resolved_system_prompt = (
                f"{prompt_instructions}\n\n{format_instruction}{no_think_suffix}"
            ).strip()
            raw_tags = self._call_llm(
                input_text,
                resolved_system_prompt,
                api_url,
                resolved_model,
                seed,
                temperature,
                max_tokens,
                timeout,
                retries,
                log_label="Danbooru Prompt",
            )
            raw_tags = sanitize_output(raw_tags)
            if not raw_tags:
                raise RuntimeError("LLM output was empty after cleaning")
        except Exception as exc:
            self._log_failure(
                exc,
                api_url,
                resolved_model,
                timeout,
                log_label="Danbooru Prompt",
            )
            normalized_error_mode = str(error_mode or "stop").casefold()
            if normalized_error_mode == "stop":
                raise RuntimeError(
                    self._failure_message(
                        exc,
                        api_url,
                        resolved_model,
                        timeout,
                        feature_name="Danbooru Prompt",
                    )
                ) from exc
            if normalized_error_mode == "empty":
                return ("", "", "")
            raw_tags = input_text
            is_fallback = True

        template = TEMPLATE_PRESETS.get(template_preset, prompt_template)
        dropped = []
        if is_fallback:
            tags = raw_tags
        elif validate_tags:
            tags, _kept, dropped = get_tag_db().validate(
                raw_tags,
                strict=strict_tags,
                fuzzy_cutoff=fuzzy_cutoff,
                min_post_count=min_post_count,
                max_tags=max_tags,
                exclude_categories=parse_categories(exclude_categories),
                sort_tags=sort_tags,
                tag_format=tag_format,
            )
        else:
            tags = format_unvalidated_tags(raw_tags, tag_format)

        prompt = apply_prompt_template(template, tags)
        print(
            f"[Danbooru Prompt] Generated {len([tag for tag in tags.split(',') if tag.strip()])} "
            f"tags; dropped {len(dropped)}"
        )
        return (prompt, tags, ", ".join(dropped))
