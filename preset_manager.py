"""Load bundled and user-authored system-prompt presets."""

from pathlib import Path


MAX_PRESET_BYTES = 64 * 1024
BUILTIN_PRESET_DIR = Path(__file__).resolve().parent / "presets"


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


def list_presets(create_user_directory=False):
    """Return built-in presets followed by user presets.

    A user preset with the same filename as a built-in remains separately
    addressable with a ``(User)`` suffix in the UI.
    """
    builtins = _load_directory(BUILTIN_PRESET_DIR, "builtin")
    user_directory = get_user_preset_dir(create=create_user_directory)
    user_presets = _load_directory(user_directory, "user")

    used_names = {preset["name"].casefold() for preset in builtins}
    for preset in user_presets:
        if preset["name"].casefold() in used_names:
            preset["name"] = f"{preset['name']} (User)"
        used_names.add(preset["name"].casefold())
    return builtins + user_presets
