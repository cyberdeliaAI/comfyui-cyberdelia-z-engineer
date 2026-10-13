"""No dependencies beyond the Python standard library and ComfyUI itself."""

import hashlib
import random
import re
from pathlib import Path


TAG = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
TAG_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
CHOICE = re.compile(r"\{([^{}\r\n]*\|[^{}\r\n]*)\}")
DEFAULT_TAGS = "hair=blonde\ntype=mature"
DEFAULT_PROMPTS = (
    "A studio portrait of an adult {type} woman with {hair} hair, soft lighting."
    "\n\n"
    "An adult {type} woman with {hair} hair, walking through a city, daylight."
    "\n\n"
    "An adult {type} woman with {hair} hair, wearing a sweater, sitting in a cafe."
)


def resolve_prompt_file(prompt_file):
    """Absolute paths work; relative paths refer to ComfyUI's input folder."""
    path = Path(prompt_file.strip()).expanduser()
    if not path.is_absolute():
        import folder_paths

        path = Path(folder_paths.get_input_directory()) / path
    if path.suffix.lower() != ".txt":
        raise ValueError("Choose a .txt file, or paste your prompts into 'prompts'.")
    return path


def read_source(prompts, prompt_file=""):
    if not prompt_file.strip():
        return prompts
    path = resolve_prompt_file(prompt_file)
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Save your prompt file as UTF-8 text.") from exc
    except OSError as exc:
        raise ValueError(f"Cannot read prompt file '{path}': {exc.strerror or exc}") from exc


def resolve_choices(text, rng=None):
    """Choose one literal alternative from each flat {red|brown|black} group."""
    if rng is None:
        return text

    def choose(match):
        return rng.choice([part.strip() for part in match.group(1).split("|")])

    return CHOICE.sub(choose, text)


def make_tags(extra_tags="", rng=None):
    tags = {}
    for number, line in enumerate(extra_tags.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not TAG_NAME.fullmatch(name):
            raise ValueError(f"Tag on line {number}: use name=value, e.g. hair=blonde.")
        if name in tags:
            raise ValueError(f"Tag '{name}' is already defined. Use each tag name once.")
        # Resolve each tag once so repeated uses share the same selected value.
        tags[name] = resolve_choices(value.strip(), rng)
    return tags


def fill_text(text, tags, rng=None):
    removed_tag = False

    def substitute(match):
        nonlocal removed_tag
        value = tags.get(match.group(1), "")
        if not value.strip():
            removed_tag = True
            return ""
        return value

    # A callback preserves literal values and performs only one substitution pass.
    rendered = TAG.sub(substitute, resolve_choices(text, rng))
    if removed_tag:
        # Clean horizontal spacing after removing optional tags, keeping the
        # prompt's line breaks intact.
        rendered = re.sub(r"[^\S\r\n]+", " ", rendered)
        rendered = re.sub(r" +(?=[,.;:!?])", "", rendered)
        rendered = re.sub(r" *\n *", "\n", rendered).strip()
    return rendered


def fill_prompts(source, tags, prompt_separator="blank line", rng=None):
    source = source.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if prompt_separator == "blank line":
        # Preserve internal line breaks when a blank line separates prompts.
        parts = re.split(r"\n[^\S\n]*\n(?:[^\S\n]*\n)*", source)
    elif prompt_separator == "one per line":
        parts = source.splitlines()
    else:
        raise ValueError("Choose 'blank line' or 'one per line' for prompt_separator.")
    blocks = [block.strip() for block in parts if block.strip()]
    if not blocks:
        raise ValueError("Add at least one prompt.")
    return [fill_text(block, tags, rng) for block in blocks]


def replace_text(prompts, search_replace="", replace_match="whole words", case_sensitive=False, rng=None):
    if replace_match not in ("whole words", "literal text"):
        raise ValueError("Choose 'whole words' or 'literal text' for replace_match.")
    rules = []
    for number, line in enumerate(search_replace.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        search, separator, replacement = line.partition("=")
        search = search.strip()
        if not separator or not search:
            raise ValueError(f"Search/replace on line {number}: use search=replacement, e.g. woman=male.")
        pattern = re.escape(search)
        if replace_match == "whole words":
            pattern = r"(?<!\w)" + pattern + r"(?!\w)"
        flags = 0 if case_sensitive else re.IGNORECASE
        # Choose once per rule, keeping repeated matches and prompt blocks consistent.
        rules.append((re.compile(pattern, flags), resolve_choices(replacement.strip(), rng)))

    output = []
    for prompt in prompts:
        had_text = bool(prompt.strip())
        # Rules run in order, after tag substitution. A callback preserves literal
        # replacement values such as backslashes instead of treating them as regex.
        for pattern, replacement in rules:
            prompt = pattern.sub(lambda match, value=replacement: value, prompt)
        if had_text and not prompt.strip():
            raise ValueError("Search/replace removed an entire prompt. Keep at least some prompt text.")
        output.append(prompt)
    return output


def select_prompts(rendered, mode="random prompt", prompt_seed=0):
    if mode == "random prompt":
        # Use a local RNG so prompt selection never changes the sampler's state.
        selected = [random.Random(prompt_seed).choice(rendered)]
    elif mode == "all prompts":
        selected = rendered
    else:
        raise ValueError("Choose 'random prompt' or 'all prompts' for mode.")
    return (selected, "\n\n".join(selected), len(selected))


def prepend_prefix(prompts, prefix, tags, rng=None):
    prefix = prefix.strip()
    if not prefix:
        return prompts
    prefix = fill_text(prefix, tags, rng)
    if not prefix.strip(", :;\t\r\n"):
        return prompts
    separator = " " if prefix.endswith((",", ":", ";")) else ", "
    return [prefix + separator + prompt if prompt.strip() else prefix.rstrip(", :;") for prompt in prompts]


class WildcardLoRAPrompts:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompts": ("STRING", {
                    "default": DEFAULT_PROMPTS, "multiline": True,
                    "dynamicPrompts": False,
                    "tooltip": "Paste prompts here. Use {hair} tags or choices such as {red|brown|black}. Choose blank-line separation or one prompt per line with prompt_separator.",
                }),
                "extra_tags": ("STRING", {
                    "default": DEFAULT_TAGS, "multiline": True, "dynamicPrompts": False,
                    "tooltip": "Define tags here, one name=value per line. Values can use choices, e.g. hair={red|brown|black}; each tag is chosen once per run. Missing or empty tags are removed from the prompt.",
                }),
            },
            "optional": {
                "prompt_file": ("STRING", {
                    "default": "", "dynamicPrompts": False,
                    "tooltip": "Optional .txt path on the ComfyUI computer. Overrides pasted prompts. Relative to ComfyUI/input.",
                }),
                "prompt_separator": (["blank line", "one per line"], {
                    "default": "blank line",
                    "tooltip": "Blank line lets each prompt span multiple lines. One per line treats each non-empty line as a separate prompt.",
                }),
                "search_replace": ("STRING", {
                    "default": "", "multiline": True, "dynamicPrompts": False,
                    "tooltip": "One search=replacement per line, e.g. straight hair={red|brown|black} hair. Choices are selected once per rule. Rules run after filling tags. An empty replacement deletes the matched text.",
                }),
                "replace_match": (["whole words", "literal text"], {
                    "default": "whole words",
                    "tooltip": "Whole words avoids replacing woman inside superwoman. Literal text matches anywhere. Search text is always literal, never a regular expression.",
                }),
                "case_sensitive": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "When disabled, woman also matches Woman and WOMAN. Replacement text is inserted exactly as entered.",
                }),
                "prefix": ("STRING", {
                    "default": "", "dynamicPrompts": False,
                    "tooltip": "Optional keyword or text at the beginning of the final prompt. Empty ignores it. Can use {trigger} tags or {red|brown|black} choices. Added after search/replace.",
                }),
                "mode": (["random prompt", "all prompts"], {
                    "default": "random prompt",
                    "tooltip": "Random prompt sends one prompt per run. All prompts processes every prompt block.",
                }),
                "prompt_seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xFFFFFFFF,
                    "control_after_generate": True,
                    "tooltip": "Controls prompt selection and {red|brown|black} choices. Set its control_after_generate to randomize for new draws each run, or fixed to repeat the result.",
                }),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "label_on": "wildcards on",
                    "label_off": "wildcards off — normal prompt",
                    "tooltip": "Turn off to send fallback_prompt once, unchanged. Prompt files, tags, replacements, prefix and selection are ignored while off.",
                }),
                "fallback_prompt": ("STRING", {
                    "default": "", "multiline": True, "dynamicPrompts": False,
                    "tooltip": "Normal prompt used when wildcards are off. Enter it here, or connect the prompt output of Cyberdelia Prompt Controls. An empty value sends one empty prompt.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompts", "preview", "prompt_count")
    OUTPUT_IS_LIST = (True, False, False)
    FUNCTION = "expand"
    CATEGORY = "Cyberdelia/Prompt"
    DESCRIPTION = "Choose one random prompt per run, fill editable tags and {option|option} choices, remove unfilled tags, apply search/replace, and optionally add a prefix. Turn wildcards off to send one normal prompt unchanged."
    SEARCH_ALIASES = ["wildcard", "lora test", "prompt template", "prompt list"]

    @classmethod
    def IS_CHANGED(cls, prompts="", extra_tags=DEFAULT_TAGS, prompt_file="", prompt_separator="blank line", search_replace="", replace_match="whole words", case_sensitive=False, prefix="", mode="random prompt", prompt_seed=0, enabled=True, fallback_prompt=""):
        if not enabled:
            # ComfyUI also checks file fingerprints before execution. Bypass
            # this read when disabled, including for a missing or invalid path.
            return ("wildcards-disabled",)
        fingerprint = "pasted-prompts"
        if prompt_file.strip():
            # Hash content, not timestamps, so edits are detected even when a file
            # retains its modification time or its size does not change.
            source = read_source(prompts, prompt_file)
            fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return (fingerprint, prompt_separator, mode, prompt_seed)

    def expand(self, prompts, extra_tags=DEFAULT_TAGS, prompt_file="", prompt_separator="blank line", search_replace="", replace_match="whole words", case_sensitive=False, prefix="", mode="random prompt", prompt_seed=0, enabled=True, fallback_prompt=""):
        if not enabled:
            # Keep one output item even in all-prompts mode, and bypass every
            # wildcard transformation so the user's normal prompt is exact.
            prompt = str(fallback_prompt or "")
            return ([prompt], prompt, 1)
        source = read_source(prompts, prompt_file)
        # Keep choice draws separate from block selection and the global RNG.
        rng = random.Random(f"choices:{prompt_seed}")
        tags = make_tags(extra_tags, rng)
        rendered = fill_prompts(source, tags, prompt_separator, rng)
        rendered = replace_text(rendered, search_replace, replace_match, case_sensitive, rng)
        rendered = prepend_prefix(rendered, prefix, tags, rng)
        return select_prompts(rendered, mode, prompt_seed)
