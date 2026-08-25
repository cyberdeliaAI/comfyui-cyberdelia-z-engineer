"""Model-independent prompt preservation and output-cleaning helpers."""

import re


THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
UNCLOSED_THINK_PATTERN = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)
CHATML_TAG_PATTERN = re.compile(
    r"<\|im_(?:start|end)\|>(?:system|user|assistant)?",
    re.IGNORECASE,
)
PROMPT_PREFIX_PATTERN = re.compile(
    r"^\s*(?:(?:here\s+is\s+)?(?:the\s+)?)?"
    r"(?:final\s+|enhanced\s+|positive\s+)?(?:image\s+)?prompt\s*[:\-]\s*",
    re.IGNORECASE,
)
NEGATIVE_SECTION_PATTERN = re.compile(
    r"\bnegative\s+prompt\s*[:\-].*$",
    re.IGNORECASE | re.DOTALL,
)
CODE_FENCE_PATTERN = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?")
QUOTE_PATTERN = re.compile(r'"([^"\n]+)"|\'([^\'\n]+)\'')
LENS_PATTERN = re.compile(
    r"\b\d+(?:\s*-\s*\d+)?\s*mm\s+f\s*/\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
CODE_PATTERN = re.compile(
    r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b"
)

COUNT_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
)
COUNT_PATTERN = re.compile(
    rf"\b(?:\d+|{'|'.join(COUNT_WORDS)})\s+"
    r"([A-Za-z][\w'-]*)(?:\s+([A-Za-z][\w'-]*))?",
    re.IGNORECASE,
)

COLOR_WORDS = (
    "amber",
    "beige",
    "black",
    "blue",
    "bronze",
    "brown",
    "copper",
    "cyan",
    "gold",
    "golden",
    "gray",
    "green",
    "grey",
    "indigo",
    "ivory",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "teal",
    "turquoise",
    "violet",
    "white",
    "yellow",
)
COLOR_PATTERN = re.compile(
    rf"\b(?:{'|'.join(COLOR_WORDS)})\s+"
    r"([A-Za-z][\w'-]*)",
    re.IGNORECASE,
)

PHRASE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "beside",
    "by",
    "for",
    "from",
    "in",
    "inside",
    "near",
    "next",
    "of",
    "on",
    "or",
    "the",
    "to",
    "under",
    "with",
}


def normalize_whitespace(text):
    """Collapse all whitespace while preserving the text content."""
    return " ".join(str(text or "").replace("\r", "\n").split())


def _unique_terms(terms):
    result = []
    seen = set()
    for term in terms:
        normalized = normalize_whitespace(term).strip(" ,.;:")
        if not normalized:
            continue
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def parse_keep_terms(value):
    """Parse comma-, semicolon-, or newline-separated exact terms."""
    return _unique_terms(re.split(r"[,;\n]+", str(value or "")))


def _term_pattern(term):
    escaped = re.escape(normalize_whitespace(term)).replace(r"\ ", r"\s+")
    prefix = r"(?<![\w-])" if term and (term[0].isalnum() or term[0] in "_-") else ""
    suffix = r"(?![\w-])" if term and (term[-1].isalnum() or term[-1] in "_-") else ""
    return re.compile(prefix + escaped + suffix, re.IGNORECASE)


def contains_term(text, term):
    """Return whether a complete term is present, not merely a substring."""
    return _term_pattern(term).search(str(text or "")) is not None


def extract_constraints(seed):
    """Extract conservative, model-independent constraints from a seed.

    The extractor intentionally limits itself to quoted text, lens/aperture
    specifications, code-like identifiers, counts, and color/object phrases.
    It does not infer names, relationships, style, or desired prompt length.
    """
    seed = normalize_whitespace(seed)
    terms = []

    for match in QUOTE_PATTERN.finditer(seed):
        terms.append(match.group(1) or match.group(2) or "")
    terms.extend(match.group(0) for match in LENS_PATTERN.finditer(seed))
    terms.extend(match.group(0) for match in CODE_PATTERN.finditer(seed))

    for match in COUNT_PATTERN.finditer(seed):
        words = match.group(0).split()
        while len(words) > 2 and words[-1].casefold() in PHRASE_STOP_WORDS:
            words.pop()
        if len(words) > 2 and words[-1].casefold().endswith("ing"):
            words.pop()
        terms.append(" ".join(words))

    for match in COLOR_PATTERN.finditer(seed):
        words = match.group(0).split()
        if len(words) > 1 and words[1].casefold() in PHRASE_STOP_WORDS:
            words = words[:1]
        color_term = " ".join(words)
        if not any(contains_term(existing, color_term) for existing in terms):
            terms.append(color_term)

    return _unique_terms(terms)


def build_preservation_instruction(keep_terms=None, constraints=None):
    """Create the small, explicit guardrail appended to the system prompt."""
    keep_terms = _unique_terms(keep_terms or [])
    constraints = _unique_terms(constraints or [])
    instructions = []
    if keep_terms:
        instructions.append(
            "Keep these user-supplied terms verbatim, character for character: "
            + "; ".join(keep_terms)
            + "."
        )
    if constraints:
        instructions.append(
            "Preserve these explicit seed constraints verbatim and integrate them naturally: "
            + "; ".join(constraints)
            + "."
        )
    if not instructions:
        return ""
    return (
        "Prompt Engineer preservation requirements for the final answer: "
        + " ".join(instructions)
        + " Do not discuss these requirements in the answer."
    )


def sanitize_output(text):
    """Remove reasoning wrappers and common chat artefacts from LLM output."""
    text = str(text or "")
    text = THINK_BLOCK_PATTERN.sub(" ", text)
    text = UNCLOSED_THINK_PATTERN.sub(" ", text)
    text = CHATML_TAG_PATTERN.sub(" ", text)
    text = NEGATIVE_SECTION_PATTERN.sub(" ", text)
    text = CODE_FENCE_PATTERN.sub(" ", text)
    text = PROMPT_PREFIX_PATTERN.sub("", text)
    text = re.sub(r"\s+,", ",", text)
    text = normalize_whitespace(text)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _append_missing(prompt, missing, connector):
    prompt = normalize_whitespace(prompt).strip()
    if not missing:
        return prompt
    if not prompt:
        return ", ".join(missing)
    base = prompt.rstrip(" ,.!?;:")
    return normalize_whitespace(f"{base}{connector}{', '.join(missing)}.")


def enforce_constraints(prompt, constraints):
    """Append any detected seed constraints that the model omitted."""
    constraints = _unique_terms(constraints or [])
    missing = [term for term in constraints if not contains_term(prompt, term)]
    return _append_missing(prompt, missing, ", with ")


def enforce_keep_terms(prompt, keep_terms):
    """Guarantee exact user-provided terms with original casing."""
    keep_terms = _unique_terms(keep_terms or [])
    missing = [term for term in keep_terms if not contains_term(prompt, term)]
    return _append_missing(prompt, missing, ", ")
