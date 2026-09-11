"""Load bundled and user-authored system and Vision prompt presets."""

from pathlib import Path


MAX_PRESET_BYTES = 64 * 1024
BUILTIN_PRESET_DIR = Path(__file__).resolve().parent / "presets"
BUILTIN_VISION_PRESET_DIR = Path(__file__).resolve().parent / "vision_presets"


def get_user_preset_dir(create=False):
    """Return the legacy-compatible directory for Prompt Engineer presets."""
    try:
        import folder_paths
    except ImportError:
        return None

    directory = Path(folder_paths.get_user_directory()) / "z_engineer" / "presets"
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_user_vision_preset_dir(create=False):
    """Return the directory for user-authored Vision prompt presets."""
    try:
        import folder_paths
    except ImportError:
        return None

    directory = Path(folder_paths.get_user_directory()) / "z_engineer" / "vision_presets"
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_preset_file(path, root):
    try:
        resolved = path.resolve()
        if resolved.parent != root.resolve() or not resolved.is_file():
            return None
        if resolved.stat().st_size > MAX_PRESET_BYTES:
            return None
        value = resolved.read_text(encoding="utf-8").strip()
        return value or None
    except (OSError, UnicodeError):
        return None


def _load_directory(directory, source):
    if directory is None or not directory.is_dir():
        return []
    presets = []
    for path in sorted(directory.glob("*.txt"), key=lambda item: item.name.casefold()):
        prompt = _read_preset_file(path, directory)
        if prompt:
            presets.append(
                {
                    "name": path.stem,
                    "prompt": prompt,
                    "source": source,
                }
            )
    return presets


def _merge_presets(builtin_directory, user_directory):
    """Return built-in presets followed by uniquely labelled user presets."""
    builtins = _load_directory(builtin_directory, "builtin")
    user_presets = _load_directory(user_directory, "user")

    used_names = {preset["name"].casefold() for preset in builtins}
    for preset in user_presets:
        if preset["name"].casefold() in used_names:
            preset["name"] = f"{preset['name']} (User)"
        used_names.add(preset["name"].casefold())
    return builtins + user_presets


def list_presets(create_user_directory=False):
    """Return built-in system presets followed by user system presets."""
    user_directory = get_user_preset_dir(create=create_user_directory)
    return _merge_presets(BUILTIN_PRESET_DIR, user_directory)


def list_vision_presets(create_user_directory=False):
    """Return built-in Vision presets followed by user Vision presets."""
    user_directory = get_user_vision_preset_dir(create=create_user_directory)
    return _merge_presets(BUILTIN_VISION_PRESET_DIR, user_directory)
