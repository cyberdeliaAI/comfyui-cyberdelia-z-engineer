"""No dependencies beyond the Python standard library and ComfyUI itself."""

import difflib
import hashlib
import logging
import os
import random
import re
from pathlib import Path


LOG_PREFIX = "[Wildcard Prompts]"
PROMPT_DIRS_ENV = "CYBERDELIA_Z_ENGINEER_PROMPT_DIRS"
MAX_PROMPT_FILE_BYTES = 10 * 1024 * 1024
# Full-line comments in prompt sources, removed together with their line break
# so a comment inside a multi-line prompt never splits it into two prompts.
COMMENT_LINE = re.compile(r"^[^\S\n]*#[^\n]*(?:\n|\Z)", re.MULTILINE)

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


def allowed_prompt_dirs():
    """ComfyUI's input folder plus folders the machine owner allows explicitly.

    Workflow values are untrusted: on a shared or --listen server, an arbitrary
    path would let anyone read text files from the ComfyUI computer.
    """
    folders = []
    try:
        import folder_paths

        folders.append(Path(folder_paths.get_input_directory()))
    except ImportError:
        pass
    for value in os.environ.get(PROMPT_DIRS_ENV, "").split(os.pathsep):
        if value.strip():
            folders.append(Path(value.strip()).expanduser())
    return [folder.resolve() for folder in folders]


def resolve_prompt_file(prompt_file):
    """Relative paths refer to ComfyUI's input folder. Every path must stay
    inside that folder or a folder listed in CYBERDELIA_Z_ENGINEER_PROMPT_DIRS."""
    path = Path(prompt_file.strip()).expanduser()
    if path.suffix.lower() != ".txt":
        raise ValueError("Choose a .txt file, or paste your prompts into 'prompts'.")
    if not path.is_absolute():
        import folder_paths

        path = Path(folder_paths.get_input_directory()) / path
    path = path.resolve()
    if not any(path == folder or folder in path.parents for folder in allowed_prompt_dirs()):
        raise ValueError(
            "Prompt files must be inside the ComfyUI input folder. To use another "
            f"folder, add it to {PROMPT_DIRS_ENV} before starting ComfyUI, or load "
            "the file with the Load .txt button."
        )
    return path


def read_source(prompts, prompt_file=""):
    if not prompt_file.strip():
        return prompts
    path = resolve_prompt_file(prompt_file)
    try:
        if path.stat().st_size > MAX_PROMPT_FILE_BYTES:
            raise ValueError(f"Prompt file '{path.name}' is larger than {MAX_PROMPT_FILE_BYTES // (1024 * 1024)} MB.")
        return path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Save your prompt file as UTF-8 text.") from exc
    except OSError as exc:
        raise ValueError(f"Cannot read prompt file '{path}': {exc.strerror or exc}") from exc


def _resolve_choices(text, rng=None):
    """Return the text with choices resolved, and whether an empty option was chosen."""
    if rng is None:
        return text, False
    chose_empty = False

    def choose(match):
        nonlocal chose_empty
        value = rng.choice([part.strip() for part in match.group(1).split("|")])
        chose_empty = chose_empty or not value
        return value

    # Resolve innermost groups first, so nested choices such as {a|{b|c}}
    # never leak braces. Each pass removes at least one brace pair, so the loop
    # always ends. Flat groups resolve in the first pass with unchanged draws.
    while True:
        resolved = CHOICE.sub(choose, text)
        if resolved == text:
            return resolved, chose_empty
        text = resolved


def resolve_choices(text, rng=None):
    """Choose one literal alternative from each {red|brown|black} group."""
    return _resolve_choices(text, rng)[0]


def tidy_removed_text(text):
    """Clean spacing and separators left behind by removed or empty values.

    Only called after something was removed, so unrelated formatting in prompts
    without removals stays exactly as written. Line breaks are preserved.
    """
    # Braces left by an undefined tag inside braces, such as {{masterpiece}}.
    text = re.sub(r"\{[^\S\r\n]*\}", "", text)
    text = re.sub(r"[^\S\r\n]+", " ", text)
    text = re.sub(r" +(?=[,.;:!?])", "", text)
    text = re.sub(r" *\n *", "\n", text).strip()
    # Comma-separated tag prompts: collapse separators left by removed values,
    # such as "photo, , blonde" or ", blonde" or "photo, blonde,".
    text = re.sub(r",(?: ?,)+", ",", text)
    text = re.sub(r"[,;]+(?=[.!?])", "", text)
    text = re.sub(r"(?m)^ *[,;]+ *", "", text)
    text = re.sub(r"(?m) *[,;]+ *$", "", text)
    return text.strip()


def warn_undefined_tags(names, tags):
    """Log template tags that were removed because no tag defines them."""
    if not names:
        return
    described = []
    for name in sorted(names, key=str.casefold):
        same_case = [tag for tag in tags if tag.casefold() == name.casefold()]
        close = same_case or difflib.get_close_matches(name, list(tags), n=1, cutoff=0.75)
        hint = f" (did you mean {{{close[0]}}}?)" if close else ""
        described.append(f"{{{name}}}{hint}")
    logging.warning(
        "%s Removed undefined tag(s): %s. Define them in extra_tags; names are "
        "case-sensitive. Define a tag with an empty value (name=) to remove it on purpose.",
        LOG_PREFIX,
        ", ".join(described),
    )


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


def fill_text(text, tags, rng=None, undefined=None):
    text, removed = _resolve_choices(text, rng)

    def substitute(match):
        nonlocal removed
        name = match.group(1)
        if name not in tags and undefined is not None:
            undefined.add(name)
        value = tags.get(name, "")
        if not value.strip():
            removed = True
            return ""
        return value

    # A callback preserves literal values and performs only one substitution pass.
    rendered = TAG.sub(substitute, text)
    # A tag can complete a choice group, as in {{hair}|bald}. Tag values were
    # already resolved, so this pass only draws for groups formed this way.
    rendered, chose_empty = _resolve_choices(rendered, rng)
    if removed or chose_empty:
        rendered = tidy_removed_text(rendered)
    return rendered


def fill_prompts(source, tags, prompt_separator="blank line", rng=None, undefined=None):
    source = source.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    # Lines starting with # are comments, as in extra_tags and search_replace.
    source = COMMENT_LINE.sub("", source).strip()
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
    return [fill_text(block, tags, rng, undefined) for block in blocks]


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
        deleted = False
        for pattern, replacement in rules:
            prompt, count = pattern.subn(lambda match, value=replacement: value, prompt)
            deleted = deleted or (count > 0 and not replacement)
        if deleted:
            # Deleting text leaves double spaces or separators behind.
            prompt = tidy_removed_text(prompt)
        if had_text and not prompt.strip():
            raise ValueError("Search/replace removed an entire prompt. Keep at least some prompt text.")
        output.append(prompt)
    return output


def select_prompts(rendered, mode="random prompt", prompt_seed=0, repeat_list=False, sequence_index=0):
    if mode == "random prompt":
        # Use a local RNG so prompt selection never changes the sampler's state.
        selected = [random.Random(prompt_seed).choice(rendered)]
    elif mode == "all prompts":
        selected = rendered
    elif mode == "sequential prompt":
        if not isinstance(sequence_index, int) or isinstance(sequence_index, bool) or sequence_index < 0:
            raise ValueError("sequence_index must be a non-negative integer.")
        if sequence_index >= len(rendered) and not repeat_list:
            # An empty string/list can still run a sampler with empty or stale
            # conditioning. Propagate ComfyUI's silent blocker instead.
            try:
                from comfy_execution.graph import ExecutionBlocker
            except ImportError as exc:
                raise RuntimeError("Sequential prompt skipping requires ComfyUI with ExecutionBlocker support. Update ComfyUI.") from exc
            blocker = ExecutionBlocker(None)
            return ([blocker], blocker, 0)
        selected = [rendered[sequence_index % len(rendered)]]
    else:
        raise ValueError("Choose 'random prompt', 'sequential prompt' or 'all prompts' for mode.")
    return (selected, "\n\n".join(selected), len(selected))


def sequence_status(sequence_index, count, repeat_list=False):
    """Describe a sequential selection for logs and the node's status label."""
    finished = sequence_index >= count and not repeat_list
    return {
        "index": sequence_index,
        "count": count,
        # One-based prompt number that was used, or None when the run was skipped.
        "prompt": None if finished else sequence_index % count + 1,
        "finished": finished,
        "repeat": bool(repeat_list),
    }


def prepend_prefix(prompts, prefix, tags, rng=None, undefined=None):
    prefix = prefix.strip()
    if not prefix:
        return prompts
    prefix = fill_text(prefix, tags, rng, undefined)
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
                    "tooltip": "Paste prompts here. Use {hair} tags or choices such as {red|brown|black}. Choose blank-line separation or one prompt per line with prompt_separator. Lines starting with # are comments.",
                }),
                "extra_tags": ("STRING", {
                    "default": DEFAULT_TAGS, "multiline": True, "dynamicPrompts": False,
                    "tooltip": "Define tags here, one name=value per line. Values can use choices, e.g. hair={red|brown|black}; each tag is chosen once per run. Missing or empty tags are removed from the prompt.",
                }),
            },
            "optional": {
                "prompt_file": ("STRING", {
                    "default": "", "dynamicPrompts": False,
                    "tooltip": "Optional .txt path on the ComfyUI computer. Overrides pasted prompts. Relative to ComfyUI/input. Files must be inside the input folder or a folder listed in CYBERDELIA_Z_ENGINEER_PROMPT_DIRS.",
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
                "mode": (["random prompt", "sequential prompt", "all prompts"], {
                    "default": "random prompt",
                    "tooltip": "Random prompt chooses one prompt per run. Sequential prompt sends the next prompt per queued workflow. All prompts is the existing list mode: every prompt block in one workflow.",
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
                    # A connected source only runs when wildcards are off.
                    "lazy": True,
                    "tooltip": "Normal prompt used when wildcards are off. Enter it here, or connect the prompt output of Cyberdelia Prompt Controls. An empty value sends one empty prompt.",
                }),
                "repeat_list": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Sequential mode only. Off skips the dependent generation chain after the last prompt; on repeats the list from the beginning.",
                }),
                "sequence_index": ("INT", {
                    "default": 0, "min": 0, "max": 0xFFFFFFFF,
                    "tooltip": "Sequential mode only. Zero selects the first prompt. Advances after each successful queue submission in the UI, also when promoted to a subgraph. Reset sequence starts over. API clients must increment this input themselves.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompts", "preview", "prompt_count")
    OUTPUT_IS_LIST = (True, False, False)
    # run() wraps expand() and adds a sequence status for the node's label.
    FUNCTION = "run"
    CATEGORY = "Cyberdelia/Prompt"
    DESCRIPTION = "Choose a random prompt, advance sequentially per queued workflow, or output all prompts as a list. Fill tags and {option|option} choices, apply search/replace and a prefix. Sequential mode skips the dependent generation chain at the end unless repeat_list is on."
    SEARCH_ALIASES = ["wildcard", "lora test", "prompt template", "prompt list"]

    def check_lazy_status(self, enabled=True, fallback_prompt=None, **_kwargs):
        # ComfyUI evaluates a lazy input only when it is requested here.
        return [] if enabled else ["fallback_prompt"]

    @classmethod
    def IS_CHANGED(cls, prompts="",extra_tags=DEFAULT_TAGS, prompt_file="", prompt_separator="blank line", search_replace="", replace_match="whole words", case_sensitive=False, prefix="", mode="random prompt", prompt_seed=0, enabled=True, fallback_prompt="", repeat_list=False, sequence_index=0):
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

    def expand(self, prompts, extra_tags=DEFAULT_TAGS, prompt_file="", prompt_separator="blank line", search_replace="", replace_match="whole words", case_sensitive=False, prefix="", mode="random prompt", prompt_seed=0, enabled=True, fallback_prompt="", repeat_list=False, sequence_index=0):
        return self._expand(prompts, extra_tags, prompt_file, prompt_separator, search_replace, replace_match, case_sensitive, prefix, mode, prompt_seed, enabled, fallback_prompt, repeat_list, sequence_index)[0]

    def run(self, prompts, extra_tags=DEFAULT_TAGS, prompt_file="", prompt_separator="blank line", search_replace="", replace_match="whole words", case_sensitive=False, prefix="", mode="random prompt", prompt_seed=0, enabled=True, fallback_prompt="", repeat_list=False, sequence_index=0):
        result, status = self._expand(prompts, extra_tags, prompt_file, prompt_separator, search_replace, replace_match, case_sensitive, prefix, mode, prompt_seed, enabled, fallback_prompt, repeat_list, sequence_index)
        if status is None:
            return result
        # ComfyUI sends "ui" data to the frontend for any node, also when the
        # dependent chain is blocked, so the node can show the sequence state.
        return {"ui": {"wildcard_sequence": [status]}, "result": result}

    def _expand(self, prompts, extra_tags, prompt_file, prompt_separator, search_replace, replace_match, case_sensitive, prefix, mode, prompt_seed, enabled, fallback_prompt, repeat_list, sequence_index):
        if not enabled:
            # Keep one output item even in all-prompts mode, and bypass every
            # wildcard transformation so the user's normal prompt is exact.
            prompt = str(fallback_prompt or "")
            return ([prompt], prompt, 1), None
        source = read_source(prompts, prompt_file)
        # Keep choice draws separate from block selection and the global RNG.
        rng = random.Random(f"choices:{prompt_seed}")
        undefined = set()
        tags = make_tags(extra_tags, rng)
        rendered = fill_prompts(source, tags, prompt_separator, rng, undefined)
        rendered = replace_text(rendered, search_replace, replace_match, case_sensitive, rng)
        rendered = prepend_prefix(rendered, prefix, tags, rng, undefined)
        warn_undefined_tags(undefined, tags)
        result = select_prompts(rendered, mode, prompt_seed, repeat_list, sequence_index)
        if mode != "sequential prompt":
            return result, None
        status = sequence_status(sequence_index, len(rendered), repeat_list)
        if status["finished"]:
            # The blocker itself is silent, so explain the skipped run here.
            logging.warning(
                "%s Sequence finished: sequence_index %d is past the last of %d prompt(s), "
                "so nodes that use this prompt were skipped. Click 'Reset sequence' or "
                "turn on repeat_list.",
                LOG_PREFIX, sequence_index, len(rendered),
            )
        else:
            logging.info(
                "%s Sequential prompt %d of %d (sequence_index %d).",
                LOG_PREFIX, status["prompt"], len(rendered), sequence_index,
            )
        return result, status
