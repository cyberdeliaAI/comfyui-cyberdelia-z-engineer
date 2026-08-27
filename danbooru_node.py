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
    "You convert a scene description into candidate Danbooru tags for an "
    "Illustrious-based SDXL anime or illustration model.\n\n"
    "Your output is passed through a strict Danbooru vocabulary validator and a "
    "separate quality-template stage.\n\n"
    "OUTPUT RULES\n\n"
    "- Return only one lowercase, comma-separated tag list.\n"
    "- Do not output sentences, explanations, headings, numbering, markdown, "
    "notes, or labels.\n"
    "- Do not repeat tags.\n"
    "- Do not invent tag-shaped phrases or use normal prose.\n"
    "- The caller separately specifies whether multi-word tags use spaces or "
    "underscores. Follow that formatting instruction.\n\n"
    "CONTENT RULES\n\n"
    "- Output content and visual-description tags only.\n"
    "- Do not add quality, resolution, score, or rating anchors such as "
    "masterpiece, best_quality, best quality, very_aesthetic, very aesthetic, "
    "amazing_quality, newest, absurdres, highres, safe, sensitive, questionable, "
    "explicit, score_9, or score_8_up. These are handled separately.\n"
    "- Convert user wording into established Danbooru concepts.\n"
    "- Prefer common, clear, visually meaningful tags over rare or ambiguous "
    "alternatives.\n"
    "- Start with an appropriate subject-count tag when possible, such as 1girl, "
    "1boy, 2girls, 1girl and 1boy, solo, multiple girls, or no humans.\n"
    "- Include canonical character and copyright tags only when the user clearly "
    "requests a known character or series.\n"
    "- Include artist tags only when explicitly requested.\n"
    "- Describe only details that can be seen in the image.\n"
    "- Express mood or personality through visible expression, pose, action, "
    "lighting, and environment tags.\n"
    "- Choose one coherent visual style and avoid conflicting styles.\n"
    "- Use only one or two compatible composition concepts.\n\n"
    "PREFERRED CONTENT ORDER\n\n"
    "subject count, character, copyright, primary visual style, hair, eyes, "
    "expression, clothing, accessories, pose or action, camera and composition, "
    "background or environment, lighting and atmosphere, additional visible "
    "details\n\n"
    "SAFETY\n\n"
    "- Never produce sexualized or suggestive tags for underage, young-looking, "
    "childlike, or age-ambiguous subjects.\n"
    "- Keep canonically underage characters fully SFW.\n"
    "- When age is ambiguous, default to safe visual content.\n\n"
    "Return tags only."
)

MODE_ENGINEERED = "engineered (LLM)"
MODE_VALIDATE = "validate tags"
MODE_RAW = "raw positive"
MODES = (MODE_ENGINEERED, MODE_VALIDATE, MODE_RAW)


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
                "mode": (list(MODES), {
                    "default": MODE_ENGINEERED,
                    "tooltip": (
                        "Engineered uses the LLM then validates. Validate tags checks "
                        "an existing tag prompt without the LLM. Raw positive returns "
                        "the prompt exactly as entered."
                    ),
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter your prompt here...",
                    "tooltip": (
                        "A natural-language description for engineered mode, or a "
                        "ready-made positive prompt for raw mode."
                    ),
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
                    "tooltip": (
                        "Controls validation in engineered mode. The validate-tags "
                        "mode always validates."
                    ),
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
        mode,
        prompt,
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
        error_mode="stop",
        retries=1,
    ):
        input_text = str(prompt or "")
        # Preserve workflows made with the earlier two-position boolean switch.
        selected_mode = (
            MODE_ENGINEERED if mode is True else MODE_RAW if mode is False else str(mode)
        )
        if selected_mode not in MODES:
            raise ValueError(f"Unknown Danbooru Prompt mode: {selected_mode!r}")

        if selected_mode == MODE_RAW:
            print("[Danbooru Prompt] Raw positive mode — using input text unchanged")
            return (input_text, input_text, "")

        if not input_text.strip():
            return ("", "", "")

        resolved_model = str(model or "").strip() or "auto"
        is_fallback = False
        if selected_mode == MODE_VALIDATE:
            raw_tags = input_text
            print("[Danbooru Prompt] Validate-tags mode — skipping the LLM")
        else:
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
                resolved_system_prompt = (
                    f"{str(system_prompt or '').strip()}\n\n{format_instruction}"
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

        dropped = []
        if is_fallback:
            tags = raw_tags
        elif selected_mode == MODE_VALIDATE or validate_tags:
            tags, _kept, dropped = get_tag_db().validate(
                raw_tags,
                strict=strict_tags,
                fuzzy_cutoff=fuzzy_cutoff,
                min_post_count=min_post_count,
                max_tags=max_tags,
                exclude_categories=parse_categories(exclude_categories),
                sort_tags=sort_tags,
                tag_format=tag_format,
                recover_subtags=selected_mode == MODE_ENGINEERED,
            )
        else:
            tags = format_unvalidated_tags(raw_tags, tag_format)

        prompt = apply_prompt_template(prompt_template, tags)
        print(
            f"[Danbooru Prompt] Generated {len([tag for tag in tags.split(',') if tag.strip()])} "
            f"tags; dropped {len(dropped)}"
        )
        return (prompt, tags, ", ".join(dropped))
