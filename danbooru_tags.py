"""Danbooru tag validation for Cyberdelia Danbooru Prompt.

Adapted from NeuralBooru's MIT-licensed validator:
https://github.com/ChrisJohnson89/ComfyUI-NeuralBooru

The bundled CSV is derived from DominikDoom/a1111-sd-webui-tagcomplete.
See THIRD_PARTY_NOTICES.md for attribution and license details.
"""

import csv
import difflib
from pathlib import Path
import re


DATA_PATH = Path(__file__).resolve().parent / "data" / "danbooru.csv"

CATEGORY_NAMES = {
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
}

EXTRA_ALIASES = {
    "silver_hair": "grey_hair",
    "silver_eyes": "grey_eyes",
    "golden_hair": "blonde_hair",
}

_WHITESPACE_PATTERN = re.compile(r"\s+")
_HAS_LETTER_PATTERN = re.compile(r"[a-z]")
_COUNT_TAG_PATTERN = re.compile(
    r"^(?:\d+(?:girls?|boys?|others?)|solo|multiple_girls|multiple_boys"
    r"|multiple_others)$"
)
_CATEGORY_ORDER = {4: 1, 3: 2, 1: 3, 0: 4, 5: 5}


def normalize_tag(tag):
    """Convert user- or LLM-written text to a canonical lookup key."""
    value = str(tag or "").strip().lower()
    value = value.replace("\\(", "(").replace("\\)", ")")
    value = _WHITESPACE_PATTERN.sub(" ", value).strip()
    return value.replace(" ", "_")


def format_tag(tag, tag_format="spaces"):
    """Render a canonical tag with spaces or underscores for the final prompt."""
    value = str(tag or "")
    if tag_format == "spaces" and _HAS_LETTER_PATTERN.search(value):
        value = value.replace("_", " ")
    return value.replace("(", "\\(").replace(")", "\\)")


def parse_categories(spec):
    """Parse comma-separated category names or numeric Danbooru codes."""
    category_codes = {name: code for code, name in CATEGORY_NAMES.items()}
    result = set()
    for part in str(spec or "").split(","):
        value = part.strip().lower()
        if not value:
            continue
        if value.isdigit():
            result.add(int(value))
        elif value in category_codes:
            result.add(category_codes[value])
        else:
            print(
                f"[Danbooru Prompt] Unknown tag category {value!r} ignored "
                f"(valid: {', '.join(category_codes)})"
            )
    return result


def _morphological_variants(tag):
    """Return conservative variants for common verb and plural forms."""
    if "_" in tag:
        head, _, tail = tag.rpartition("_")
        prefix = f"{head}_"
    else:
        prefix, tail = "", tag

    variants = []
    for suffix, replacement in (
        ("ing", ""),
        ("ing", "e"),
        ("ed", ""),
        ("ed", "e"),
        ("es", ""),
        ("s", ""),
    ):
        if tail.endswith(suffix) and len(tail) - len(suffix) >= 3:
            variants.append(prefix + tail[: -len(suffix)] + replacement)
    if not tail.endswith("s") and len(tail) >= 3:
        variants.append(prefix + tail + "s")
    return variants


def _sort_group(tag, category):
    if category == 0 and _COUNT_TAG_PATTERN.match(tag):
        return 0
    return _CATEGORY_ORDER.get(category, 4)


class DanbooruTagDB:
    """Lazy-friendly in-memory index of canonical tags and aliases."""

    def __init__(self, path=DATA_PATH):
        self.canonical = {}
        self.aliases = {}
        self._fuzzy_keys = None
        self._load(Path(path))

    def _load(self, path):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if not row or not row[0].strip():
                    continue
                original = row[0].strip()
                category = (
                    int(row[1])
                    if len(row) > 1 and row[1].strip().isdigit()
                    else 0
                )
                post_count = (
                    int(row[2])
                    if len(row) > 2 and row[2].strip().isdigit()
                    else 0
                )
                canonical = normalize_tag(original)
                if not canonical:
                    continue
                self.canonical[canonical] = (original, category, post_count)
                if len(row) > 3 and row[3]:
                    for alias in row[3].split(","):
                        normalized_alias = normalize_tag(alias)
                        if (
                            normalized_alias
                            and normalized_alias not in self.canonical
                            and normalized_alias not in self.aliases
                        ):
                            self.aliases[normalized_alias] = canonical

        for alias, canonical in EXTRA_ALIASES.items():
            if canonical in self.canonical and alias not in self.canonical:
                self.aliases.setdefault(alias, canonical)

    def __len__(self):
        return len(self.canonical)

    def _lookup(self, tag):
        if tag in self.canonical:
            return tag
        return self.aliases.get(tag)

    def resolve(self, candidate, fuzzy_cutoff=0.0):
        """Resolve a candidate through exact, alias, morphology, then fuzzy lookup."""
        normalized = normalize_tag(candidate)
        if not normalized:
            return None

        direct = self._lookup(normalized)
        if direct:
            return direct

        for variant in _morphological_variants(normalized):
            match = self._lookup(variant)
            if match:
                return match

        if fuzzy_cutoff and fuzzy_cutoff > 0:
            if self._fuzzy_keys is None:
                self._fuzzy_keys = list(self.canonical)
            matches = difflib.get_close_matches(
                normalized,
                self._fuzzy_keys,
                n=1,
                cutoff=fuzzy_cutoff,
            )
            if matches:
                return matches[0]
        return None

    def extract(self, candidate, fuzzy_cutoff=0.0):
        """Recover real tags embedded in an otherwise invalid phrase."""
        tokens = [
            word
            for word in re.split(r"\s+", str(candidate or "").strip().lower())
            if word
        ]
        if len(tokens) < 2:
            return []

        found = []
        index = 0
        while index < len(tokens):
            matched = False
            for end in range(len(tokens), index, -1):
                phrase = "_".join(tokens[index:end])
                match = (
                    self.resolve(phrase, fuzzy_cutoff)
                    if end - index > 1
                    else self._lookup(phrase)
                )
                if match:
                    found.append(match)
                    index = end
                    matched = True
                    break
            if not matched:
                index += 1
        return found

    def validate(
        self,
        text,
        strict=True,
        fuzzy_cutoff=0.0,
        min_post_count=0,
        max_tags=0,
        exclude_categories=None,
        sort_tags=True,
        tag_format="spaces",
        recover_subtags=True,
    ):
        """Validate comma-separated candidates and return output, kept, dropped."""
        if tag_format not in {"spaces", "underscores"}:
            raise ValueError("tag_format must be 'spaces' or 'underscores'")

        excluded = set(exclude_categories or ())
        kept = []
        dropped = []
        seen = set()

        def accept(canonical):
            _original, category, post_count = self.canonical[canonical]
            if category in excluded:
                return False
            if min_post_count and post_count < min_post_count:
                return False
            if canonical in seen:
                return True
            if max_tags and len(kept) >= max_tags:
                return False
            seen.add(canonical)
            kept.append((canonical, category))
            return True

        candidates = [
            part.strip() for part in str(text or "").split(",") if part.strip()
        ]
        for index, candidate in enumerate(candidates):
            if not candidate:
                continue
            if max_tags and len(kept) >= max_tags:
                dropped.extend(candidates[index:])
                break

            canonical = self.resolve(candidate, fuzzy_cutoff)
            if canonical is not None:
                if not accept(canonical):
                    dropped.append(candidate)
                continue

            if not strict:
                normalized = normalize_tag(candidate)
                if normalized not in seen:
                    seen.add(normalized)
                    kept.append((normalized, 0))
                continue

            recovered = self.extract(candidate, fuzzy_cutoff) if recover_subtags else []
            if recovered:
                results = [accept(tag) for tag in recovered]
                if any(results):
                    # The candidate did not survive intact. Report it even when
                    # useful sub-tags were recovered so lost modifiers remain visible.
                    dropped.append(candidate)
                    continue

            dropped.append(candidate)

        if sort_tags:
            kept.sort(key=lambda item: _sort_group(item[0], item[1]))

        formatted = [format_tag(tag, tag_format) for tag, _category in kept]
        return ", ".join(formatted), formatted, dropped


_DATABASE = None
_DATABASE_ERROR = None


def get_tag_db():
    """Load the tag database once and retain a useful error for the caller."""
    global _DATABASE, _DATABASE_ERROR
    if _DATABASE is None and _DATABASE_ERROR is None:
        try:
            _DATABASE = DanbooruTagDB()
        except Exception as exc:
            _DATABASE_ERROR = exc
    if _DATABASE is None:
        raise RuntimeError(
            f"Danbooru tag database could not be loaded from {DATA_PATH}: "
            f"{_DATABASE_ERROR}"
        ) from _DATABASE_ERROR
    return _DATABASE
